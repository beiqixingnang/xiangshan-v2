"""Review and map every vendored Scala source under upstream/src."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from v2_all_source_scan import masked_scala


ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "validation/v2-all-source-scan-seed.json"
OUTPUT = ROOT / "validation/v2-all-source-core-scan.json"
BUILD_ROOT = "python/Program-System/System-Build/Build-Cpu/"
CORE_ROOT = BUILD_ROOT + "Cpu-Core/"
MEMORY_ROOT = BUILD_ROOT + "Cpu-Memory/"


def core(name: str) -> str:
    return CORE_ROOT + "Cpu-Core-" + name + "-Hardware.py"


def memory(name: str) -> str:
    return MEMORY_ROOT + "Cpu-Memory-" + name + "-Hardware.py"


TOP = core("Top")
BACKEND_TOP = core("Backend.Top")
BACKEND_CONTROL = core("Backend.SmallControl.Family")
BACKEND_DECODE = core("Backend.Decode.ControlFamily")
BACKEND_FUNC = core("Backend.Exu.FuncUnit")
BACKEND_VECTOR = core("Backend.Datapath.VectorFamily")
ISSUE_ENTRIES = core("Backend.Issue.Entries")
MEM_BLOCK = memory("Memory.MemBlock")
FRONTEND_BRIDGE = memory("Memory.FrontendBridge")
LSQ_FAMILY = memory("Memory.Mmu.Lsq.Family")
STORE_FAMILY = memory("Memory.Store.Family")
PREFETCH_FAMILY = memory("Memory.Prefetch.Family")
MEMORY_VECTOR = memory("Memory.Vector.Family")


NEW_TARGETS: dict[str, dict[str, Any]] = {
    TOP: {
        "responsibility": "Complete UHSCTop assembly from the core, tile, system bus, interrupt, trace, reset, and optional SoC configuration contracts.",
        "required_configuration_modes": [
            "DefaultConfig and KunminghuV2Config, including the legal minimal variants",
            "XSNoCTop, XSNoCDiffTop, and XSTileDiffTop topology branches",
            "FPGA and non-FPGA options, optional CHI/L2, external LLC selection",
            "separated buses/device mode, private CLINT, IMSIC bus choice, async bridges",
            "WFI clock gate, power-down handshake, DFT/MBIST/SRAM-control ports",
            "SoC address maps, hart/core count, interrupt source count, and trace geometry",
        ],
        "needed_companion_dependencies": [
            core("Top.UHSC.Roots"), core("Top.UHSCore.Parent"),
            core("Top.UHSTile.IntBuffer.Family"),
            core("Device.PeripheralFamily"), core("Device.InterruptFamily"),
            core("Device.DebugFamily"), memory("Device.AxiMemoryFamily"),
        ],
    },
    core("Device.PeripheralFamily"): {
        "responsibility": "AXI peripheral endpoints for storage, keyboard, serial ports, and video; each endpoint keeps its own register and backpressure behavior.",
        "required_configuration_modes": [
            "AXI address range and beat width per endpoint",
            "UART and UART16550 divisor, register, and interrupt behavior",
            "keyboard scan-code input and register readback",
            "VGA/HDMI timing, frame-buffer geometry, and pixel access",
            "flash and dummy-SD command/address/data response modes",
        ],
        "needed_companion_dependencies": [
            core("Dependency.Rocket.Protocol"), core("Dependency.Chisel.Decoupled"),
        ],
    },
    core("Device.InterruptFamily"): {
        "responsibility": "PLIC, APLIC/IMSIC bus adapters, CLINT/TIMER/SYSCNT counters, interrupt wiring, and asynchronous time/interrupt crossings.",
        "required_configuration_modes": [
            "hart count, interrupt source count, priority/threshold and address ranges",
            "AXI versus TileLink IMSIC transport and optional TEE IMSIC mapping",
            "private/shared CLINT, timer compare width, and asynchronous crossing depth",
            "APLIC group/member strides and per-hart address translation",
        ],
        "needed_companion_dependencies": [
            core("Dependency.ChiselAIA.Interface"), core("Dependency.Rocket.Protocol"),
            core("Device.PeripheralFamily"),
        ],
    },
    core("Device.DebugFamily"): {
        "responsibility": "Debug-module, JTAG/DMI, simulation JTAG, and debug-memory interfaces with their reset, request, and response state.",
        "required_configuration_modes": [
            "debug-module enable, DMI transport, JTAG enable, hart count, and reset vector",
            "simulation-only debug transport versus product-facing debug pins",
        ],
        "needed_companion_dependencies": [
            core("Dependency.Rocket.Jtag"), core("Dependency.Difftest.Interface"),
            core("Dependency.Difftest.StateFamily"),
        ],
    },
    memory("Device.AxiMemoryFamily"): {
        "responsibility": "AXI slave memory and RAM endpoints, including burst sequencing, byte writes, IDs, range behavior, and an explicit external simulation-memory boundary.",
        "required_configuration_modes": [
            "address sets, executable flag, beatBytes, burstLen, memory capacity",
            "Amaranth memory versus injected external simulation model",
            "single/multiple outstanding read and write request modes where source permits",
        ],
        "needed_companion_dependencies": [
            core("Dependency.Rocket.Protocol"), core("Dependency.Chisel.Decoupled"),
            core("Dependency.Difftest.Interface"),
        ],
    },
    memory("Memory.EncryptionFamily"): {
        "responsibility": "AXI memory-encryption request pipelines, key/tweak derivation, cacheable and uncacheable write/read paths, and key-table state.",
        "required_configuration_modes": [
            "PAddrBits, KeyIDBits, power-of-two MemencPipes, and HasDelayNoencryption",
            "cacheable versus uncacheable access, AXI ID allocation, and partial-write merge",
            "tweak AES rounds, GF128 transform, key expansion, and key-table lookup/update",
        ],
        "needed_companion_dependencies": [
            core("Dependency.Rocket.Protocol"), core("Dependency.Chisel.Decoupled"),
            memory("Memory.Mmu.Lsq.Family"),
        ],
    },
    memory("Cache.Dcache.DataArrayFamily"): {
        "responsibility": "DCache banked and duplicated data arrays, row/way addressing, read/write enables, ECC payloads, and SRAM control behavior.",
        "required_configuration_modes": [
            "DCacheSets, DCacheWays, DCacheBanks, DCacheSetDiv, row width, and ECC width",
            "MBIST, SRAM-control, clock-gate, single-port, read-hold, and reset behavior",
            "partial bank reads, way masks, delayed errors, and read/write conflict limits",
        ],
        "needed_companion_dependencies": [
            memory("Memory.Dcache.MetaArray"), memory("Cache.Dcache.Meta.TagArray"),
        ],
    },
    memory("Cache.Dcache.MainpipeFamily"): {
        "responsibility": "DCache main-pipeline request arbitration and stage state for load/store, probe, refill, AMO, miss, replacement, ECC, and reservation paths.",
        "required_configuration_modes": [
            "S0-S3 stage latency, stage-ready backpressure, and set-conflict arbitration",
            "bank masks, full/partial stores, probe/refill priority, and force-write behavior",
            "LR/SC reservation invalidation, ECC injection/error forwarding, bloom filters",
            "store-wait threshold, flush/error/replay paths, and delayed pipeline metadata",
        ],
        "needed_companion_dependencies": [
            memory("Cache.Dcache.DataArrayFamily"), memory("Memory.Dcache.MetaArray"),
            memory("Cache.Dcache.Meta.TagArray"), memory("Memory.Dcache.MissQueue.Family"),
            STORE_FAMILY,
        ],
    },
    memory("Cache.WayPredictionFamily"): {
        "responsibility": "Cache way-prediction tables and conflict predictors for instruction and data caches, including MRU, MMRU, and hashed-tag update paths.",
        "required_configuration_modes": [
            "cache kind, number of ports, sets, ways, virtual-tag width, and algorithm selection",
            "lookup, replay-carry, tag-write, invalidation, and hash-conflict update priorities",
        ],
        "needed_companion_dependencies": [
            memory("Cache.Dcache.DataArrayFamily"), memory("Memory.MemBlock"),
        ],
    },
    memory("Memory.PipelineFamily"): {
        "responsibility": "Load, store, hybrid, and atomic memory-pipeline units with translation, issue, replay, dependency, forwarding, and writeback state.",
        "required_configuration_modes": [
            "load/store pipeline widths, outstanding queue sizes, writeback widths, and issue widths",
            "MMU/TLB responses, store-to-load forwarding, atomics, replay, and misalignment",
            "cacheable/uncacheable requests, exception ordering, cancellation, flush, and error paths",
        ],
        "needed_companion_dependencies": [
            LSQ_FAMILY, STORE_FAMILY, memory("Memory.Lsqueue.LoadQueueData"),
            memory("Memory.Lsqueue.StoreQueueData"), memory("Memory.Vector.Family"),
            memory("Memory.MemCommon-Pipeline"),
        ],
    },
}


ROUTES: dict[str, str] = {
    "upstream/src/main/scala/top/Top.scala": TOP,
    "upstream/src/main/scala/top/XSNoCTop.scala": TOP,
    "upstream/src/main/scala/top/Configs.scala": TOP,
    "upstream/src/main/scala/top/BusPerfMonitor.scala": TOP,
    "upstream/src/main/scala/system/SoC.scala": TOP,
    "upstream/src/main/scala/xiangshan/Parameters.scala": TOP,
    "upstream/src/main/scala/xiangshan/XSTile.scala": core("Top.UHSC.Roots"),
    "upstream/src/main/scala/xiangshan/XSTileWrap.scala": core("Top.UHSC.Roots"),
    "upstream/src/main/scala/xiangshan/L2Top.scala": core("Top.UHSC.Roots"),
    "upstream/src/main/scala/xiangshan/XSCore.scala": core("Top.UHSCore.Parent"),
    "upstream/src/main/scala/xiangshan/backend/Backend.scala": BACKEND_TOP,
    "upstream/src/main/scala/xiangshan/backend/BackendParams.scala": BACKEND_TOP,
    "upstream/src/main/scala/xiangshan/backend/Bundles.scala": BACKEND_TOP,
    "upstream/src/main/scala/xiangshan/backend/CtrlBlock.scala": BACKEND_CONTROL,
    "upstream/src/main/scala/xiangshan/backend/ctrlblock/LsInfo.scala": BACKEND_CONTROL,
    "upstream/src/main/scala/xiangshan/backend/ctrlblock/MemCtrl.scala": BACKEND_TOP,
    "upstream/src/main/scala/xiangshan/backend/dispatch/NewDispatch.scala": BACKEND_TOP,
    "upstream/src/main/scala/xiangshan/backend/datapath/DataConfig.scala": core("Backend.Datapath.DataSource"),
    "upstream/src/main/scala/xiangshan/backend/datapath/RdConfig.scala": core("Backend.Datapath.DataSource"),
    "upstream/src/main/scala/xiangshan/backend/datapath/WbConfig.scala": core("Backend.Datapath.DataSource"),
    "upstream/src/main/scala/xiangshan/backend/datapath/WakeUpConfig.scala": ISSUE_ENTRIES,
    "upstream/src/main/scala/xiangshan/backend/datapath/WbArbiterParams.scala": core("Backend.Datapath.WbArbiter"),
    "upstream/src/main/scala/xiangshan/backend/datapath/OldestFirstArbiter.scala": core("Dependency.Chisel.Arbiter"),
    "upstream/src/main/scala/xiangshan/backend/datapath/PcTargetMem.scala": BACKEND_TOP,
    "upstream/src/main/scala/xiangshan/backend/datapath/RFReadArbiter.scala": core("Backend.Regfile.Regfile"),
    "upstream/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala": core("Backend.Regfile.Regfile"),
    "upstream/src/main/scala/xiangshan/backend/datapath/WbFuBusyTable.scala": core("Backend.Regfile.Regfile"),
    "upstream/src/main/scala/xiangshan/backend/decode/VecDecoder.scala": BACKEND_DECODE,
    "upstream/src/main/scala/xiangshan/backend/exu/ExeUnitParams.scala": BACKEND_FUNC,
    "upstream/src/main/scala/xiangshan/backend/exu/ExuBlock.scala": BACKEND_TOP,
    "upstream/src/main/scala/xiangshan/backend/fu/Fence.scala": BACKEND_FUNC,
    "upstream/src/main/scala/xiangshan/backend/fu/FunctionUnit.scala": BACKEND_FUNC,
    "upstream/src/main/scala/xiangshan/backend/fu/FuConfig.scala": BACKEND_FUNC,
    "upstream/src/main/scala/xiangshan/backend/fu/FuType.scala": BACKEND_FUNC,
    "upstream/src/main/scala/xiangshan/backend/fu/CSR.scala": core("Backend.Fu.NewCSR.ControlFamily"),
    "upstream/src/main/scala/xiangshan/backend/fu/fpu/FpNonPipedFuncUnit.scala": core("Backend.Fu.FloatingPoint.Family"),
    "upstream/src/main/scala/xiangshan/backend/fu/fpu/FpPipedFuncUnit.scala": core("Backend.Fu.FloatingPoint.Family"),
    "upstream/src/main/scala/xiangshan/backend/fu/fpu/FPU.scala": core("Backend.Fu.FloatingPoint.Family"),
    "upstream/src/main/scala/xiangshan/backend/fu/fpu/FPUSubModule.scala": core("Backend.Fu.FloatingPoint.Family"),
    "upstream/src/main/scala/xiangshan/backend/fu/fpu/IntFPToVec.scala": core("Backend.Fu.FloatingPoint.Family"),
    "upstream/src/main/scala/xiangshan/backend/fu/fpu/Bundles.scala": core("Backend.Fu.FloatingPoint.Family"),
    "upstream/src/main/scala/xiangshan/backend/fu/vector/Bundles.scala": BACKEND_VECTOR,
    "upstream/src/main/scala/xiangshan/backend/fu/vector/Utils.scala": BACKEND_VECTOR,
    "upstream/src/main/scala/xiangshan/backend/fu/vector/VecNonPipedFuncUnit.scala": BACKEND_VECTOR,
    "upstream/src/main/scala/xiangshan/backend/fu/vector/VecPipedFuncUnit.scala": BACKEND_VECTOR,
    "upstream/src/main/scala/xiangshan/backend/issue/IssueBlockParams.scala": ISSUE_ENTRIES,
    "upstream/src/main/scala/xiangshan/backend/issue/SchdBlockParams.scala": ISSUE_ENTRIES,
    "upstream/src/main/scala/xiangshan/backend/issue/IssueQueue.scala": ISSUE_ENTRIES,
    "upstream/src/main/scala/xiangshan/backend/issue/MultiWakeupQueue.scala": ISSUE_ENTRIES,
    "upstream/src/main/scala/xiangshan/backend/issue/OthersEntry.scala": ISSUE_ENTRIES,
    "upstream/src/main/scala/xiangshan/backend/issue/WakeupQueue.scala": ISSUE_ENTRIES,
    "upstream/src/main/scala/xiangshan/backend/issue/EntryBundles.scala": ISSUE_ENTRIES,
    "upstream/src/main/scala/xiangshan/backend/issue/EnqEntry.scala": ISSUE_ENTRIES,
    "upstream/src/main/scala/xiangshan/backend/issue/Scheduler.scala": BACKEND_TOP,
    "upstream/src/main/scala/xiangshan/backend/regfile/PregParams.scala": core("Backend.Regfile.Regfile"),
    "upstream/src/main/scala/xiangshan/backend/rename/Rename.scala": core("Backend.Rob.Rename.Trace-Family"),
    "upstream/src/main/scala/xiangshan/backend/rename/RenameTable.scala": core("Backend.Rob.Rename.Trace-Family"),
    "upstream/src/main/scala/xiangshan/backend/rename/Snapshot.scala": core("Backend.Rob.Rename.Trace-Family"),
    "upstream/src/main/scala/xiangshan/backend/rename/BusyTable.scala": core("Backend.Rob.Rename.Trace-Family"),
    "upstream/src/main/scala/xiangshan/backend/rename/CompressUnit.scala": core("Backend.Rob.Rename.Trace-Family"),
    "upstream/src/main/scala/xiangshan/backend/rename/freelist/BaseFreeList.scala": core("Backend.Rob.Rename.Trace-Family"),
    "upstream/src/main/scala/xiangshan/backend/rename/freelist/MEFreeList.scala": core("Backend.Rob.Rename.Trace-Family"),
    "upstream/src/main/scala/xiangshan/backend/rename/freelist/StdFreeList.scala": core("Backend.Rob.Rename.Trace-Family"),
    "upstream/src/main/scala/xiangshan/backend/rob/Rob.scala": BACKEND_CONTROL,
    "upstream/src/main/scala/xiangshan/backend/rob/RobBundles.scala": BACKEND_CONTROL,
    "upstream/src/main/scala/xiangshan/backend/rob/Rab.scala": BACKEND_CONTROL,
    "upstream/src/main/scala/xiangshan/backend/rob/ExceptionGen.scala": BACKEND_CONTROL,
    "upstream/src/main/scala/xiangshan/backend/rob/VTypeBuffer.scala": BACKEND_CONTROL,
    "upstream/src/main/scala/xiangshan/backend/rob/DiffRatStateBuffer.scala": core("Dependency.Difftest.StateFamily"),
    "upstream/src/main/scala/xiangshan/backend/trace/Interface.scala": core("Dependency.Difftest.Interface"),
    "upstream/src/main/scala/xiangshan/backend/trace/Trace.scala": core("Dependency.Difftest.StateFamily"),
    "upstream/src/main/scala/xiangshan/backend/trace/TraceBuffer.scala": core("Dependency.Difftest.StateFamily"),
    "upstream/src/main/scala/xiangshan/cache/dcache/data/AbstractDataArray.scala": memory("Cache.Dcache.DataArrayFamily"),
    "upstream/src/main/scala/xiangshan/cache/dcache/data/BankedDataArray.scala": memory("Cache.Dcache.DataArrayFamily"),
    "upstream/src/main/scala/xiangshan/cache/dcache/data/DuplicatedDataArray.scala": memory("Cache.Dcache.DataArrayFamily"),
    "upstream/src/main/scala/xiangshan/cache/dcache/mainpipe/MainPipe.scala": memory("Cache.Dcache.MainpipeFamily"),
    "upstream/src/main/scala/xiangshan/cache/dcache/mainpipe/AtomicsReplayUnit.scala": memory("Cache.Dcache.MainpipeFamily"),
    "upstream/src/main/scala/xiangshan/cache/dcache/mainpipe/Probe.scala": memory("Cache.Dcache.MainpipeFamily"),
    "upstream/src/main/scala/xiangshan/cache/dcache/mainpipe/WritebackQueue.scala": memory("Cache.Dcache.MainpipeFamily"),
    "upstream/src/main/scala/xiangshan/cache/dcache/CtrlUnit.scala": memory("Cache.Dcache.MainpipeFamily"),
    "upstream/src/main/scala/xiangshan/cache/wpu/VictimList.scala": memory("Cache.WayPredictionFamily"),
    "upstream/src/main/scala/xiangshan/cache/wpu/WPU.scala": memory("Cache.WayPredictionFamily"),
    "upstream/src/main/scala/xiangshan/cache/wpu/WPUWrapper.scala": memory("Cache.WayPredictionFamily"),
    "upstream/src/main/scala/xiangshan/mem/pipeline/AtomicsUnit.scala": memory("Memory.PipelineFamily"),
    "upstream/src/main/scala/xiangshan/mem/pipeline/HybridUnit.scala": memory("Memory.PipelineFamily"),
    "upstream/src/main/scala/xiangshan/mem/pipeline/LoadUnit.scala": memory("Memory.PipelineFamily"),
    "upstream/src/main/scala/xiangshan/mem/pipeline/StoreUnit.scala": memory("Memory.PipelineFamily"),
    "upstream/src/main/scala/xiangshan/mem/MemBlock.scala": MEM_BLOCK,
    "upstream/src/main/scala/xiangshan/mem/Bundles.scala": MEM_BLOCK,
    "upstream/src/main/scala/xiangshan/mem/MemCommon.scala": memory("Memory.MemCommon-Pipeline"),
    "upstream/src/main/scala/xiangshan/mem/MaskedDataModule.scala": memory("Memory.MemCommon-Pipeline"),
    "upstream/src/main/scala/xiangshan/mem/lsqueue/LoadQueue.scala": LSQ_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/lsqueue/LoadQueueRAR.scala": LSQ_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/lsqueue/LoadQueueRAW.scala": LSQ_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/lsqueue/LoadQueueReplay.scala": LSQ_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/lsqueue/LoadExceptionBuffer.scala": LSQ_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/lsqueue/LoadMisalignBuffer.scala": LSQ_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/lsqueue/LSQWrapper.scala": LSQ_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/lsqueue/FreeList.scala": LSQ_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/lsqueue/VirtualLoadQueue.scala": LSQ_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/lsqueue/LoadQueueUncache.scala": memory("Memory.Lsqueue.Uncache"),
    "upstream/src/main/scala/xiangshan/mem/lsqueue/StoreQueue.scala": STORE_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/lsqueue/StoreMisalignBuffer.scala": STORE_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/lsqueue/StoreQueueData.scala": memory("Memory.Lsqueue.StoreQueueData"),
    "upstream/src/main/scala/xiangshan/mem/lsqueue/LoadQueueData.scala": memory("Memory.Lsqueue.LoadQueueData"),
    "upstream/src/main/scala/xiangshan/mem/mdp/StoreSet.scala": STORE_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/mdp/WaitTable.scala": STORE_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/sbuffer/DatamoduleResultBuffer.scala": STORE_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/sbuffer/FakeSbuffer.scala": STORE_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/sbuffer/Sbuffer.scala": STORE_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/sbuffer/StorePrefetchBursts.scala": STORE_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/prefetch/BasePrefecher.scala": PREFETCH_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/prefetch/FDP.scala": PREFETCH_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/prefetch/L1PrefetchComponent.scala": PREFETCH_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/prefetch/L1PrefetchInterface.scala": PREFETCH_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/prefetch/L1StreamPrefetcher.scala": PREFETCH_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/prefetch/L1StridePrefetcher.scala": PREFETCH_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/prefetch/PrefetcherMonitor.scala": PREFETCH_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/prefetch/SMSPrefetcher.scala": PREFETCH_FAMILY,
    "upstream/src/main/scala/xiangshan/mem/vector/VecBundle.scala": MEMORY_VECTOR,
    "upstream/src/main/scala/xiangshan/mem/vector/VecCommon.scala": MEMORY_VECTOR,
    "upstream/src/main/scala/xiangshan/mem/vector/VfofBuffer.scala": MEMORY_VECTOR,
    "upstream/src/main/scala/xiangshan/mem/vector/VMergeBuffer.scala": MEMORY_VECTOR,
    "upstream/src/main/scala/xiangshan/mem/vector/VSegmentUnit.scala": MEMORY_VECTOR,
    "upstream/src/main/scala/xiangshan/mem/vector/VSplit.scala": MEMORY_VECTOR,
    "upstream/src/main/scala/device/AXI4DummySD.scala": core("Device.PeripheralFamily"),
    "upstream/src/main/scala/device/AXI4Flash.scala": core("Device.PeripheralFamily"),
    "upstream/src/main/scala/device/AXI4Keyboard.scala": core("Device.PeripheralFamily"),
    "upstream/src/main/scala/device/AXI4UART.scala": core("Device.PeripheralFamily"),
    "upstream/src/main/scala/device/AXI4UART16550.scala": core("Device.PeripheralFamily"),
    "upstream/src/main/scala/device/AXI4VGA.scala": core("Device.PeripheralFamily"),
    "upstream/src/main/scala/device/AXI4IntrGenerator.scala": core("Device.InterruptFamily"),
    "upstream/src/main/scala/device/AXI4Plic.scala": core("Device.InterruptFamily"),
    "upstream/src/main/scala/device/imsic_axi_top.scala": core("Device.InterruptFamily"),
    "upstream/src/main/scala/device/standalone/StandAloneCLINT.scala": core("Device.InterruptFamily"),
    "upstream/src/main/scala/device/standalone/StandAlonePLIC.scala": core("Device.InterruptFamily"),
    "upstream/src/main/scala/device/standalone/StandAloneSYSCNT.scala": core("Device.InterruptFamily"),
    "upstream/src/main/scala/device/standalone/StandAloneDevice.scala": TOP,
    "upstream/src/main/scala/device/SYSCNT.scala": core("Device.InterruptFamily"),
    "upstream/src/main/scala/device/TimeAsync.scala": core("Device.InterruptFamily"),
    "upstream/src/main/scala/device/TIMER.scala": core("Device.InterruptFamily"),
    "upstream/src/main/scala/device/AXI4Timer.scala": core("Device.InterruptFamily"),
    "upstream/src/main/scala/device/TLTimer.scala": core("Device.InterruptFamily"),
    "upstream/src/main/scala/device/RocketDebugWrapper.scala": core("Device.DebugFamily"),
    "upstream/src/main/scala/device/standalone/StandAloneDebugModule.scala": core("Device.DebugFamily"),
    "upstream/src/main/scala/device/AXI4Memory.scala": memory("Device.AxiMemoryFamily"),
    "upstream/src/main/scala/device/AXI4RAM.scala": memory("Device.AxiMemoryFamily"),
    "upstream/src/main/scala/device/AXI4SlaveModule.scala": memory("Device.AxiMemoryFamily"),
    "upstream/src/main/scala/device/MemEncrypt.scala": memory("Memory.EncryptionFamily"),
    "upstream/src/main/scala/device/MemEncryptUtil.scala": memory("Memory.EncryptionFamily"),
    "upstream/src/main/scala/device/TLPMA/TLPMA.scala": LSQ_FAMILY,
    "upstream/src/main/scala/utils/AXI4Lite.scala": core("Device.PeripheralFamily"),
    "upstream/src/main/scala/utils/OverrideableQueue.scala": core("Dependency.Chisel.Decoupled"),
    "upstream/src/main/scala/utils/PipeWithFlush.scala": core("Dependency.Chisel.Decoupled"),
    "upstream/src/main/scala/utils/PowerSwitchBuffer.scala": TOP,
    "upstream/src/main/scala/utils/LowPowerState.scala": TOP,
    "upstream/src/main/scala/utils/ArbiterHelper.scala": core("Dependency.Chisel.Arbiter"),
    "upstream/src/main/scala/utils/DebugMem.scala": core("Device.DebugFamily"),
}


DECLARATION_OWNER_OVERRIDES: dict[tuple[str, str], str] = {
    ("upstream/src/main/scala/xiangshan/backend/Backend.scala", "BackendMemIO"): core("Top.UHSCore.Parent"),
    ("upstream/src/main/scala/xiangshan/backend/Backend.scala", "TopToBackendBundle"): core("Top.UHSCore.Parent"),
    ("upstream/src/main/scala/xiangshan/backend/Backend.scala", "BackendToTopBundle"): core("Top.UHSCore.Parent"),
    ("upstream/src/main/scala/xiangshan/backend/Backend.scala", "BackendIO"): core("Top.UHSCore.Parent"),
    ("upstream/src/main/scala/xiangshan/mem/MemBlock.scala", "FrontendBridge"): FRONTEND_BRIDGE,
    ("upstream/src/main/scala/xiangshan/mem/MemBlock.scala", "InstrUncacheBuffer"): FRONTEND_BRIDGE,
    ("upstream/src/main/scala/xiangshan/mem/MemBlock.scala", "InstrUncacheBufferImpl"): FRONTEND_BRIDGE,
    ("upstream/src/main/scala/xiangshan/mem/MemBlock.scala", "ICacheBuffer"): FRONTEND_BRIDGE,
    ("upstream/src/main/scala/xiangshan/mem/MemBlock.scala", "ICacheBufferImpl"): FRONTEND_BRIDGE,
    ("upstream/src/main/scala/xiangshan/mem/MemBlock.scala", "ICacheCtrlBuffer"): FRONTEND_BRIDGE,
    ("upstream/src/main/scala/xiangshan/mem/MemBlock.scala", "ICacheCtrlBufferImpl"): FRONTEND_BRIDGE,
}


SPECIAL_FEATURES: dict[str, list[str]] = {
    "upstream/src/main/scala/device/AXI4Memory.scala": [
        "Preserve AXI AR/AW/W/B/R ready-valid handshakes, request holding, burst address/ID bookkeeping, byte strobes, outstanding counters, response ordering, and reset behavior.",
        "Preserve the source configuration for address sets, memory size, beatBytes, and burstLen; keep the Difftest/C++/DPI memory model as an explicit injected host boundary and do not embed its generated C++ or Verilog text.",
    ],
    "upstream/src/main/scala/device/AXI4RAM.scala": [
        "Preserve AXI single-slave idle/read/write/response state, incrementing burst limits, byte-mask writes, address range checks, and the registered ID/user response fields.",
        "Preserve beatBytes, burstLen, executable, and useBlackBox choices; express the selected RAM behavior in Amaranth and keep external memory models behind explicit configuration.",
    ],
    "upstream/src/main/scala/device/MemEncrypt.scala": [
        "Preserve request/response channel staging and backpressure for AXI read/write encryption, cacheable versus uncacheable writes, partial-write merge, key IDs, address alignment, and uncache commit state.",
        "Preserve MemencPipes power-of-two validation, PAddrBits/KeyIDBits constraints, tweak/key pipeline latency, key-table state, and reset/flush/error behavior.",
    ],
    "upstream/src/main/scala/device/MemEncryptUtil.scala": [
        "Preserve AES round/key expansion, GF128/tweak arithmetic, tweak-table lookup/update, byte routing, queue order, and every valid-ready pipeline stage used by the encryption parent.",
    ],
    "upstream/src/main/scala/xiangshan/cache/dcache/data/BankedDataArray.scala": [
        "Preserve bank/way/set address decomposition, single-port SRAM timing, bank and way enables, write masks, read latency, duplicated-port behavior, ECC bits, delayed errors, and MBIST/SRAM-control choices.",
    ],
    "upstream/src/main/scala/xiangshan/cache/dcache/mainpipe/MainPipe.scala": [
        "Preserve the S0-S3 request pipeline, source priority across probe/refill/store/atomic inputs, bank/set conflict suppression, store starvation threshold, data/meta/tag requests, partial-store read/modify/write, LR/SC reservation, and error-injection paths.",
        "Preserve stage-valid/ready latency, flush/error forwarding, bloom-filter queries, ECC responses, replacement updates, and the force-write and reset modes.",
    ],
    "upstream/src/main/scala/xiangshan/cache/wpu/WPU.scala": [
        "Preserve the MRU and MMRU set/way tables, UTAG hash/valid entries, lookup prediction, conflict repair, replay-carry and tag-write updates, port ordering, and algorithm selection.",
    ],
    "upstream/src/main/scala/xiangshan/mem/pipeline/LoadUnit.scala": [
        "Preserve load address generation, translation and permission response handling, data alignment/extension, forwarding, exception ordering, replay/backpressure, cancellation, and load writeback timing.",
    ],
    "upstream/src/main/scala/xiangshan/mem/pipeline/StoreUnit.scala": [
        "Preserve store address/data formation, translation, misalignment, store-queue allocation, byte masks, flush/exception behavior, and commit-to-writeback ordering.",
    ],
    "upstream/src/main/scala/xiangshan/mem/pipeline/HybridUnit.scala": [
        "Preserve the shared load/store issue paths, atomic and cache-operation selection, multi-stage valid state, replay, queue pressure, and shared writeback/exception arbitration.",
    ],
    "upstream/src/main/scala/xiangshan/mem/pipeline/AtomicsUnit.scala": [
        "Preserve supported AMO/LR/SC opcode selection, operand width/sign rules, reservation and retry behavior, memory handshake, exception handling, and completion latency.",
    ],
    "upstream/src/main/scala/system/SoC.scala": [
        "Expose SoCParameters/CVMParameters as serializable product configuration, including PMA and memory ranges, CLINT/PLIC/APLIC/IMSIC ranges, CHI and asynchronous bridge modes, L3 choice, hart/interrupt counts, private CLINT, WFI clock gate, and power-down options.",
        "Preserve SoC interrupt-node attachment, memory/MMIO port contracts, address translation, trace geometry, and parameter validation; configuration records do not substitute for the connected SoC hardware behavior.",
    ],
    "upstream/src/main/scala/xiangshan/Parameters.scala": [
        "Expose XSCoreParameters as the explicit source of XLEN/VLEN/ELEN, fetch/decode/rename/commit widths, predictor/cache/TLB sizes, issue/ROB/RAB/LSQ sizes, functional-unit enables, vector-memory widths, WPU options, and prefetch modes.",
    ],
    "upstream/src/main/scala/xiangshan/XSCore.scala": [
        "Preserve the Frontend-Backend-MemBlock integration graph and all bidirectional interfaces for redirect, CSR, MMU, LSQ, writeback, cache, interrupt, debug, trace, flush, reset, and performance events.",
    ],
    "upstream/src/main/scala/top/Top.scala": [
        "Build UHSCTop from the configured XSTile/SoC roots and preserve clock/reset, hart ID, memory, MMIO, interrupt, trace, debug, DFT, and optional diff-top ports with their exact directions and widths.",
    ],
    "upstream/src/main/scala/top/XSNoCTop.scala": [
        "Preserve alternate NoC top branches: async clock/reset synchronization, separate bus and debug modes, IMSIC/CLINT attachment, trace, low-power, WFI clock gating, interrupt wakeup collection, power-down handshake, and tile/CHI connectivity.",
    ],
    "upstream/src/main/scala/top/Configs.scala": [
        "Represent each supported config composition as a named serializable mode, including minimal/default, cache/L3/debug, CHI, Kunminghu V2, NoC/difftest, and FPGA variants; do not port the Scala CLI/config constructor machinery as RTL.",
    ],
    "upstream/src/main/scala/xiangshan/cache/dcache/DCacheWrapper.scala": [
        "Preserve DCache public request/response bundles, cache operation and uncache paths, refill/release, load-store forwarding, miss-queue arbitration, AMO hooks, and wrapper-facing diplomacy/clock/reset behavior.",
    ],
    "upstream/src/main/scala/xiangshan/mem/MemBlock.scala": [
        "Preserve MemBlock's FrontendBridge, instruction uncache, L1/L2, MMU/PTW, LSQ, store buffer, prefetch, interrupt, error, and Backend boundary wiring for the full configured parameter family.",
    ],
}


HOST_ONLY = {
    "upstream/src/main/scala/top/ArgParser.scala",
    "upstream/src/main/scala/top/Generator.scala",
    "upstream/src/main/scala/top/XiangShanStage.scala",
    "upstream/src/main/scala/top/YamlParser.scala",
    "upstream/src/main/scala/xiangshan/transforms/Helpers.scala",
    "upstream/src/main/scala/xiangshan/transforms/NestedPrefixModulesAnnotation.scala",
    "upstream/src/main/scala/xiangshan/transforms/PrintControl.scala",
    "upstream/src/main/scala/xiangshan/transforms/PrintModuleName.scala",
    "upstream/src/main/scala/utils/DataDontCareNode.scala",
    "upstream/src/main/scala/utils/DebugIdentityNode.scala",
    "upstream/src/main/scala/utils/EnumUtils.scala",
    "upstream/src/main/scala/utils/MapUtils.scala",
    "upstream/src/main/scala/utils/OptionWrapper.scala",
    "upstream/src/main/scala/utils/SeqUtils.scala",
    "upstream/src/main/scala/utils/TLDump.scala",
    "upstream/src/main/scala/utils/Trigger.scala",
    "upstream/src/main/scala/utils/VerilogAXI4LiteRecord.scala",
    "upstream/src/main/scala/utils/VerilogAXI4Record.scala",
}

TEST_ONLY = {
    "upstream/src/main/scala/xiangshan/backend/decode/DecodeTest.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/VsetTop.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/VsetRef.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/VsetModuleMain.scala",
    "upstream/src/main/scala/xiangshan/backend/issue/MultiWakeupQueueMain.scala",
    "upstream/src/main/scala/xiangshan/backend/issue/DataArrayMain.scala",
    "upstream/src/main/scala/xiangshan/backend/issue/IssueQueueMain.scala",
    "upstream/src/main/scala/xiangshan/backend/SchedulerMain.scala",
    "upstream/src/main/scala/xiangshan/backend/BackendMain.scala",
    "upstream/src/main/scala/xiangshan/backend/DataPathMain.scala",
    "upstream/src/main/scala/xiangshan/XSTester.scala",
    "upstream/src/main/scala/cache/WpuTest.scala",
}

INACTIVE_COMMENT_ONLY = {
    "upstream/src/main/scala/xiangshan/frontend/Bim.scala",
    "upstream/src/main/scala/xiangshan/frontend/RAS.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/vector/VFPU.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/vector/VIAluFix.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/vector/VIMacU.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/vector/VIPU.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/vector/VPerm.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/vector/VPUSubModule.scala",
}

CONFIG_PATHS = {
    "upstream/src/main/scala/top/Configs.scala",
    "upstream/src/main/scala/xiangshan/Parameters.scala",
    "upstream/src/main/scala/system/SoC.scala",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def existing_builds() -> set[str]:
    return {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / BUILD_ROOT).rglob("*.py")
        if path.is_file()
    }


def source_classification(path: str, record: dict[str, Any], masked: str) -> tuple[str, str]:
    if path.startswith("upstream/src/test/") or path in TEST_ONLY:
        return "TEST_ONLY", "Scala test, test harness, reference generator, or main-scope test fixture; its assertions and stimuli inform direct-test coverage but do not become product RTL."
    if path in HOST_ONLY:
        return "HOST_TOOL", "Scala elaboration/compiler/annotation/serialization helper used by the upstream host flow; preserve only the resulting hardware contract in its real Build owner, not this host implementation."
    if path in INACTIVE_COMMENT_ONLY and not masked.strip():
        return "DECLARATION_SUPPORT", "The file is present in the vendored source set but its contents are commented out and contain no active Scala declaration or executable hardware behavior."
    if path in CONFIG_PATHS or any("Config" in item["name"] or "Params" in item["name"] or "Parameters" in item["name"] for item in record["declarations"]):
        if record["hardware_markers"] or record["locked_modules"]:
            return "MIXED_HARDWARE_SUPPORT", "The source combines explicit configuration/parameter records with Chisel hardware or locked elaboration; preserve both the serializable configuration modes and the active port/state behavior."
        return "ELABORATION_CONFIG", "The source declares hardware selection, parameter, or elaboration modes without an independent circuit; represent supported values in an explicit Build configuration API."
    if path == "upstream/src/main/scala/device/standalone/StandAloneDevice.scala":
        return "MIXED_HARDWARE_SUPPORT", "The source combines standalone hardware module wiring with an argument parser and host entry point; preserve the hardware boundary and leave the host launcher out of RTL."
    if any(token in masked for token in ("cppExtModule", "DPI-C", "HasBlackBoxResource", "ExtModule", "HasExtModuleInline", "DifftestMem", "BlackBox")):
        return "MIXED_HARDWARE_SUPPORT", "The source contains executable Chisel hardware together with an external host/black-box or generated-implementation boundary; map the hardware behavior and keep that boundary explicit."
    if record["hardware_markers"] or record["locked_modules"]:
        return "HARDWARE_BEHAVIOR", "Active Chisel module, state, port, or parameterized hardware behavior is present; the source-level module duties remain in scope even when a locked specialization does not instantiate a branch."
    return "DECLARATION_SUPPORT", "The source supplies hardware-facing bundles, constants, parameter types, or pure support functions; preserve the contract in the owning Amaranth Build without inventing a standalone circuit."


def fallback_route(path: str, existing: set[str]) -> str | None:
    if path in ROUTES:
        return ROUTES[path]
    tail = path.removeprefix("upstream/src/main/scala/")
    stem = Path(tail).stem
    if tail.startswith("xiangshan/backend/fu/NewCSR/"):
        if stem == "CSRModule":
            return core("Backend.Fu.NewCSR.CSRModule")
        if stem in {"CSRPermitModule", "PMPEntryModule", "CSRPMP", "CSRPMA", "PMAEntryModule", "CSRCustom"}:
            return core("Backend.Fu.PMP.Family") if "PMP" in stem or "PMA" in stem else core("Backend.Fu.NewCSR.CSRPermit")
        if stem == "SstcInterruptGen":
            return core("Backend.Fu.NewCSR.SstcInterruptGen")
        if stem in {"Debug", "DebugLevel", "CSRDocDump", "CSRAnnotation", "ExceptionBundle", "InterruptBundle"}:
            return core("Backend.Fu.NewCSR.DebugFamily")
        return core("Backend.Fu.NewCSR.ControlFamily")
    if tail.startswith("xiangshan/backend/fu/wrapper/"):
        return {
            "Alu": core("Backend.Fu.AluDataModule"),
            "BranchUnit": core("Backend.Fu.BranchModule"),
            "CSR": core("Backend.Fu.NewCSR.ControlFamily"),
            "DivUnit": core("Backend.Fu.SRT16Divider"),
            "FALU": core("Backend.Fu.FloatingPoint.Family"),
            "FCVT": core("Backend.Fu.FloatingPoint.Family"),
            "FDivSqrt": core("Backend.Fu.FloatingPoint.Family"),
            "FMA": core("Backend.Fu.FloatingPoint.Family"),
            "JumpUnit": core("Backend.Fu.JumpDataModule"),
            "MulUnit": core("Backend.FinalTwo.Family"),
            "VFALU": BACKEND_VECTOR,
            "VFDivSqrt": BACKEND_VECTOR,
            "VFMA": BACKEND_VECTOR,
            "VCVT": BACKEND_VECTOR,
            "VIAluFix": BACKEND_VECTOR,
            "VIDiv": BACKEND_VECTOR,
            "VIMacU": BACKEND_VECTOR,
            "VIPU": BACKEND_VECTOR,
            "VPPU": BACKEND_VECTOR,
            "VSet": BACKEND_VECTOR,
        }.get(stem, BACKEND_VECTOR)
    if tail.startswith("xiangshan/backend/fu/vector/utils/"):
        target = {
            "MaskExtrator": core("Backend.Fu.Vector.Utils.MaskExtrator"),
            "ScalaDupToVector": core("Backend.Fu.Vector.Utils.ScalaDupToVector"),
            "UIntToCont0s": core("Backend.Fu.Vector.Utils.UIntToCont0s"),
            "UIntToCont1s": core("Backend.Fu.Vector.Utils.UIntToCont1s"),
            "VecDataSplitModule": core("Backend.Fu.Vector.Utils.VecDataSplitModule"),
        }.get(stem, BACKEND_VECTOR)
        return target
    if tail.startswith("xiangshan/backend/fu/vector/"):
        return BACKEND_VECTOR
    if tail.startswith("xiangshan/backend/fu/"):
        return {
            "Alu": core("Backend.Fu.AluDataModule"),
            "Bku": core("Backend.Fu.Util.CryptoUtils"),
            "Branch": core("Backend.Fu.BranchModule"),
            "CSR": core("Backend.Fu.NewCSR.ControlFamily"),
            "Fence": BACKEND_FUNC,
            "FunctionUnit": BACKEND_FUNC,
            "FuncUnit": BACKEND_FUNC,
            "FuConfig": BACKEND_FUNC,
            "FuType": BACKEND_FUNC,
            "Jump": core("Backend.Fu.JumpDataModule"),
            "Multiplier": core("Backend.FinalTwo.Family"),
            "PMA": core("Backend.Fu.PMP.Family"),
            "PMP": core("Backend.Fu.PMP.Family"),
            "Radix2Divider": core("Backend.Fu.SRT16Divider"),
            "SRT4Divider": core("Backend.Fu.SRT16Divider"),
            "SRT16Divider": core("Backend.Fu.SRT16Divider"),
            "Vsetu": BACKEND_VECTOR,
        }.get(stem, BACKEND_FUNC)
    if tail.startswith("xiangshan/backend/issue/"):
        return {
            "AgeDetector": core("Backend.Issue.AgeDetector"),
            "NewAgeDetector": core("Backend.Issue.AgeDetector"),
            "DataArray": core("Backend.Issue.DataArray"),
            "DeqPolicy": core("Backend.Issue.DeqPolicy"),
            "EnqPolicy": core("Backend.Issue.EnqPolicy"),
            "FuBusyTableRead": core("Backend.Issue.FuBusyTableRead"),
            "ImmExtractor": core("Backend.Issue.ImmExtractor"),
            "Entries": ISSUE_ENTRIES,
            "EntryBundles": ISSUE_ENTRIES,
            "IssueQueue": ISSUE_ENTRIES,
            "IssueBlockParams": ISSUE_ENTRIES,
            "SchdBlockParams": ISSUE_ENTRIES,
            "EnqEntry": ISSUE_ENTRIES,
            "OthersEntry": ISSUE_ENTRIES,
            "WakeupQueue": ISSUE_ENTRIES,
            "MultiWakeupQueue": ISSUE_ENTRIES,
            "Scheduler": BACKEND_TOP,
        }.get(stem, ISSUE_ENTRIES)
    if tail.startswith("xiangshan/backend/regcache/"):
        return core("Backend.Regcache.AgeFamily")
    if tail.startswith("xiangshan/backend/regfile/"):
        return core("Backend.Regfile.Regfile")
    if tail.startswith("xiangshan/backend/rename/"):
        return core("Backend.Rob.Rename.Trace-Family")
    if tail.startswith("xiangshan/backend/rob/"):
        return {
            "CommitStuckCounter": core("Backend.Rob.CommitStuckCounter"),
            "RobDeqPtrWrapper": core("Backend.Rob.PtrWrappers"),
            "RobEnqPtrWrapper": core("Backend.Rob.PtrWrappers"),
            "RobPtrWrappers": core("Backend.Rob.PtrWrappers"),
        }.get(stem, BACKEND_CONTROL)
    if tail.startswith("xiangshan/backend/trace/"):
        return core("Dependency.Difftest.Interface") if stem == "Interface" else core("Dependency.Difftest.StateFamily")
    if tail.startswith("xiangshan/backend/datapath/"):
        return {
            "BypassNetwork": core("Backend.Datapath.BypassPipeFamily"),
            "DataSource": core("Backend.Datapath.DataSource"),
            "DataPath": BACKEND_TOP,
            "NewPipelineConnect": core("Backend.Datapath.NewPipelineConnect"),
            "Og2ForVector": BACKEND_VECTOR,
            "VldMergeUnit": core("Backend.Datapath.VldMergeUnit"),
            "WbArbiter": core("Backend.Datapath.WbArbiter"),
            "WbFuBusyTable": core("Backend.Regfile.Regfile"),
        }.get(stem, BACKEND_TOP)
    if tail.startswith("xiangshan/backend/decode/"):
        return {
            "Instructions": core("Backend.Decode.Instructions"),
            "RiscvInst": core("Backend.Decode.Isa.Bitfield.RiscvInst"),
            "predecode": core("Backend.Decode.Isa.Predecode.PreDecodeInst"),
            "CSRs": core("Backend.Decode.Isa.CSRs"),
        }.get(stem, BACKEND_DECODE)
    if tail.startswith("xiangshan/backend/exu/"):
        return core("Backend.Exu.FuncUnit") if stem in {"ExeUnit", "ExeUnitParams"} else BACKEND_TOP
    if tail.startswith("xiangshan/backend/"):
        return BACKEND_CONTROL if stem in {"CtrlBlock", "RedirectGenerator"} else BACKEND_TOP
    if tail.startswith("xiangshan/frontend/"):
        if "/icache/" in tail:
            return {
                "ICacheMshr": core("Frontend.Icache.ICacheMshr"),
                "ICacheReplacer": core("Frontend.Icache.ICacheReplacer"),
                "InstrMMIOEntry": core("Frontend.Icache.InstrMMIOEntry"),
                "InstrUncache": core("Frontend.Icache.InstrUncache"),
                "Prefetch": core("Frontend.Icache.Prefetch.Family"),
                "Utils": core("Frontend.Icache.Utils"),
            }.get(stem, core("Frontend.Top"))
        if "/ifu/" in tail:
            return core("Frontend.Ifu.RvcExpander")
        if "/bpu/" in tail:
            return core("Frontend.Bpu.Parent")
        return core("Frontend.Top")
    if tail.startswith("xiangshan/cache/"):
        if "/dcache/mainpipe/" in tail:
            if stem == "AMOALU":
                return memory("Cache.Dcache.Mainpipe.AMOALU")
            if stem == "MissQueue":
                return memory("Memory.Dcache.MissQueue.Family")
            return memory("Cache.Dcache.MainpipeFamily")
        if "/dcache/meta/" in tail:
            if stem == "TagArray":
                return memory("Cache.Dcache.Meta.TagArray")
            return memory("Memory.Dcache.MetaArray")
        if "/dcache/data/" in tail:
            return memory("Cache.Dcache.DataArrayFamily")
        if "/dcache/storepipe/" in tail:
            return STORE_FAMILY
        if "/dcache/loadpipe/" in tail:
            return MEM_BLOCK
        if "/dcache/" in tail:
            return MEM_BLOCK
        if "/mmu/" in tail:
            return LSQ_FAMILY
        if "/wpu/" in tail:
            return memory("Cache.WayPredictionFamily")
        return MEM_BLOCK
    if tail.startswith("xiangshan/mem/"):
        if "/pipeline/" in tail:
            return memory("Memory.PipelineFamily")
        if "/lsqueue/" in tail:
            if stem == "LoadQueueData":
                return memory("Memory.Lsqueue.LoadQueueData")
            if stem == "StoreQueueData":
                return memory("Memory.Lsqueue.StoreQueueData")
            if "Uncache" in stem:
                return memory("Memory.Lsqueue.Uncache")
            if stem.startswith("Store") or stem in {"FreeList"}:
                return STORE_FAMILY
            return LSQ_FAMILY
        if "/prefetch/" in tail:
            return PREFETCH_FAMILY
        if "/sbuffer/" in tail or "/mdp/" in tail:
            return STORE_FAMILY
        if "/vector/" in tail:
            return MEMORY_VECTOR
        if stem in {"MemBlock", "Bundles"}:
            return MEM_BLOCK
        return core("Dependency.Difftest.StateFamily") if stem == "MemTrace" else MEM_BLOCK
    if tail.startswith("xiangshan/"):
        return core("Top.UHSC.Roots") if stem in {"L2Top", "XSTile", "XSTileWrap"} else core("Top.UHSCore.Parent")
    if tail.startswith("device/standalone/"):
        return core("Device.InterruptFamily") if "Debug" not in stem else core("Device.DebugFamily")
    if tail.startswith("device/"):
        if stem in {"MemEncrypt", "MemEncryptUtil"}:
            return memory("Memory.EncryptionFamily")
        if stem in {"AXI4Memory", "AXI4RAM", "AXI4SlaveModule"}:
            return memory("Device.AxiMemoryFamily")
        if stem in {"RocketDebugWrapper"}:
            return core("Device.DebugFamily")
        if stem in {"AXI4IntrGenerator", "AXI4Plic", "imsic_axi_top", "AXI4Timer", "SYSCNT", "TimeAsync", "TIMER", "TLTimer"}:
            return core("Device.InterruptFamily")
        if stem == "TLPMA":
            return LSQ_FAMILY
        return core("Device.PeripheralFamily")
    if tail.startswith("system/"):
        return TOP
    if tail.startswith("top/"):
        if stem in {"ArgParser", "Generator", "XiangShanStage", "YamlParser"}:
            return None
        if stem == "ExternalLLC":
            return memory("Dependency.OpenLLC.Bridge")
        return TOP
    if tail.startswith("utils/"):
        return {
            "AXI4Lite": core("Device.PeripheralFamily"),
            "ArbiterHelper": core("Dependency.Chisel.Arbiter"),
            "DebugMem": core("Device.DebugFamily"),
            "PowerSwitchBuffer": TOP,
            "LowPowerState": TOP,
            "OverrideableQueue": core("Dependency.Chisel.Decoupled"),
            "PipeWithFlush": core("Dependency.Chisel.Decoupled"),
        }.get(stem, core("Dependency.Utility"))
    if tail.startswith("cache/"):
        return MEM_BLOCK
    if tail.startswith("fu/"):
        return BACKEND_FUNC
    return None


def declaration_owner(path: str, declaration: dict[str, Any], default: str | None) -> str | None:
    if path == "upstream/src/main/scala/device/standalone/StandAloneDevice.scala" and declaration["name"] in {"ArgParser", "Main"}:
        return None
    override = DECLARATION_OWNER_OVERRIDES.get((path, declaration["name"]))
    if override:
        return override
    return default


def source_features(path: str, record: dict[str, Any], masked: str, classification: str) -> list[str]:
    features = list(SPECIAL_FEATURES.get(path, []))
    declared = [f"{item['kind']} {item['name']}" for item in record["declarations"]]
    if declared:
        features.append("Primary source declarations: " + ", ".join(declared) + ".")
    methods = list(dict.fromkeys(re.findall(r"\bdef\s+([A-Za-z][A-Za-z0-9_$]*)\s*(?:\[|\()", masked)))
    if methods:
        features.append("Methods with source duties to preserve: " + ", ".join(methods) + ".")
    registers = list(dict.fromkeys(re.findall(
        r"\bval\s+([A-Za-z][A-Za-z0-9_$]*)\s*(?::[^=\n]+)?=\s*(?:RegInit|RegNext|RegEnable|Reg|Counter|Mem|SyncReadMem|Queue)\b",
        masked,
    )))
    if registers:
        features.append("Sequential/queue/memory state declared in source: " + ", ".join(registers) + ".")
    config_fields = list(dict.fromkeys(re.findall(
        r"\b([A-Za-z][A-Za-z0-9_$]*)\s*:\s*(?:Boolean|Int|Long|String|Seq|Option|Map|AddressSet|WPUParameters|TLBParameters)\b\s*=",
        masked,
    )))
    if config_fields:
        features.append("Source configuration fields/defaults to make explicit: " + ", ".join(config_fields) + ".")
    if classification == "ELABORATION_CONFIG":
        features.append("Keep configuration serializable and explicit; do not translate Chisel Config inheritance, command parsing, environment probing, or host elaboration as circuit logic.")
    elif classification == "HOST_TOOL":
        features.append("No RTL owner: retain this source as an audited host/compiler utility disposition; only its resulting stable hardware contract can be represented by an Amaranth Build.")
    elif classification == "TEST_ONLY":
        features.append("Test-only stimuli/assertions belong to future direct tests and reference checks, not to the Build implementation.")
    elif classification == "DECLARATION_SUPPORT" and not declared:
        features.append("No active class/object/trait declaration was found after masking comments and strings; retain the file disposition without claiming hardware behavior.")
    if record["locked_modules"]:
        features.append("Locked-reference module names are scope hints only; every mapped module still needs a real local behavior owner and is not counted as implemented here: " + ", ".join(record["locked_modules"]) + ".")
    return features or ["The file is explicitly inventoried; see its classification reason and declaration owners for the non-RTL or support disposition."]


def source_reason(path: str, record: dict[str, Any], classification: str, base_reason: str) -> str:
    if path in INACTIVE_COMMENT_ONLY:
        return base_reason + " Active behavior is not migrated from commented legacy text."
    if classification in {"HARDWARE_BEHAVIOR", "MIXED_HARDWARE_SUPPORT"}:
        symbols = ", ".join(item["name"] for item in record["declarations"][:12])
        lock_note = f" Locked-reference names recorded: {len(record['locked_modules'])}." if record["locked_modules"] else " No locked module name is associated with this file."
        return f"{base_reason} Active symbols reviewed: {symbols or 'none detected by the declaration scanner'}.{lock_note} Historical path matches are candidate hints only."
    return base_reason + " Historical mappings and reference counts do not grant implementation credit."


def build_fragment() -> dict[str, Any]:
    seed = read_json(SEED)
    selected = sorted((row for row in seed["files"] if row["path"].startswith("upstream/src/") and row["path"].endswith(".scala")), key=lambda row: row["path"])
    expected_paths = {row["path"] for row in seed["files"] if row["path"].startswith("upstream/src/") and row["path"].endswith(".scala")}
    rows: list[dict[str, Any]] = []
    target_sources: dict[str, set[str]] = defaultdict(set)
    target_symbols: dict[str, set[str]] = defaultdict(set)
    target_config: dict[str, set[str]] = defaultdict(set)
    for record in selected:
        path = record["path"]
        source_path = ROOT / path
        raw = source_path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != record["sha256"]:
            raise ValueError("source hash changed since seed: " + path)
        source = raw.decode("utf-8-sig")
        masked = masked_scala(source)
        classification, base_reason = source_classification(path, record, masked)
        route = ROUTES.get(path)
        if route is None and classification not in {"TEST_ONLY", "HOST_TOOL"} and path not in INACTIVE_COMMENT_ONLY:
            route = fallback_route(path, existing_builds())
        owner_targets: list[str] = []
        declaration_rows: list[dict[str, str]] = []
        if classification in {"HARDWARE_BEHAVIOR", "MIXED_HARDWARE_SUPPORT"} and route is None:
            raise ValueError("hardware source has no route: " + path)
        for declaration in record["declarations"]:
            owner = declaration_owner(path, declaration, route)
            if owner:
                owner_targets.append(owner)
                disposition = "primary_hardware_behavior_owner" if classification in {"HARDWARE_BEHAVIOR", "MIXED_HARDWARE_SUPPORT"} else "configuration_or_contract_api_owner"
                target_symbols[owner].add(declaration["name"])
                if classification == "ELABORATION_CONFIG":
                    target_config[owner].add(Path(path).name.removesuffix(".scala") + " configuration values/modes")
            else:
                disposition = {
                    "TEST_ONLY": "test_fixture_or_assertion_only_no_product_rtl",
                    "HOST_TOOL": "host_compiler_or_generator_only_no_product_rtl",
                    "DECLARATION_SUPPORT": "inactive_or_nonbehavioral_source_no_standalone_rtl",
                    "ELABORATION_CONFIG": "host_elaboration_record_without_independent_build_api",
                    "MIXED_HARDWARE_SUPPORT": "host_support_part_of_mixed_source",
                    "HARDWARE_BEHAVIOR": "needs_review_missing_primary_owner",
                }[classification]
            declaration_rows.append({"name": declaration["name"], "kind": declaration["kind"], "python_target": owner or "", "disposition": disposition})
        target_list = sorted(set(owner_targets))
        if route and not record["declarations"] and classification in {"HARDWARE_BEHAVIOR", "MIXED_HARDWARE_SUPPORT"}:
            target_list = [route]
        for target in target_list:
            target_sources[target].add(path)
        review_findings = []
        if path in INACTIVE_COMMENT_ONLY:
            review_findings.append("Comment-only legacy implementation was inspected and explicitly receives no Build owner; confirm this stays non-executable in the locked source commit.")
        if classification == "MIXED_HARDWARE_SUPPORT":
            review_findings.append("Review the split between source-owned behavior/configuration and host/black-box support before bulk rewrite; no source C++/SV payload may be copied into Python.")
        if route and route not in existing_builds() and route not in NEW_TARGETS:
            review_findings.append("Selected candidate target path is absent on disk; retain it as a planned rewrite target and validate its exact naming/path before the aggregate freeze.")
        row = {
            "path": path,
            "root": "src",
            "sha256": digest,
            "scala_lines": record["lines"],
            "declarations": record["declarations"],
            "locked_module_definitions": record["locked_modules"],
            "historical_mapping_candidates_not_implementation": record["historical_mapping_candidates_not_implementation"],
            "classification": classification,
            "reason": source_reason(path, record, classification, base_reason),
            "python_targets": target_list,
            "declaration_owners": declaration_rows,
            "feature_obligations": source_features(path, record, masked, classification),
            "scope_claim": "ALL_SOURCE_PLANNED_NOT_IMPLEMENTED",
        }
        if review_findings:
            row["review_findings"] = review_findings
        rows.append(row)
    if {row["path"] for row in rows} != expected_paths:
        raise ValueError("partition does not match upstream/src exact Scala set")
    current = existing_builds()
    all_target_paths = set(target_sources)
    all_target_paths.update(path for path in NEW_TARGETS if path in target_sources)
    python_rows = []
    for target in sorted(all_target_paths):
        metadata = NEW_TARGETS.get(target, {})
        sources = sorted(target_sources[target])
        symbols = sorted(target_symbols[target])
        if metadata.get("required_configuration_modes"):
            modes = metadata["required_configuration_modes"]
        else:
            modes = sorted(target_config[target])
        if not modes:
            modes = ["Preserve every source-declared parameter default and legal branch represented by the owned Scala source set."]
        responsibility = metadata.get("responsibility") or (
            "Owns the actual source-backed behavior and parameter/interface duties for "
            + ", ".join(Path(item).stem for item in sources[:10])
            + (" and additional files" if len(sources) > 10 else "")
            + ("; primary hardware symbols: " + ", ".join(symbols[:16]) if symbols else "; declaration/configuration support only")
            + "."
        )
        dependencies = metadata.get("needed_companion_dependencies", [])
        python_rows.append({
            "path": target,
            "existing": target in current,
            "responsibility": responsibility,
            "sources": sources,
            "hardware_symbols": symbols,
            "required_configuration_modes": sorted(set(modes)),
            "owned_file_count": len(sources),
            "needed_companion_dependencies": sorted(set(dependencies)),
        })
    classifications = Counter(row["classification"] for row in rows)
    declarations = [owner for row in rows for owner in row["declaration_owners"]]
    ownership_counts = Counter((owner["kind"], owner["name"]) for row in rows for owner in row["declaration_owners"])
    seed_declarations = Counter((decl["kind"], decl["name"]) for row in selected for decl in row["declarations"])
    if ownership_counts != seed_declarations:
        raise ValueError("declaration owner Counter differs from source declarations")
    return {
        "kind": "V2_ALL_SOURCE_CORE_SCAN_FRAGMENT",
        "source_commit": seed["source_commit"],
        "scope": "exact upstream/src/**/*.scala files, including main, test, configuration, host tooling, inactive sources, and hardware support",
        "source_file_count": len(rows),
        "scala_line_count": sum(row["scala_lines"] for row in rows),
        "class_object_trait_declaration_count": len(declarations),
        "locked_module_definition_count": sum(len(row["locked_module_definitions"]) for row in rows),
        "classification_counts": dict(sorted(classifications.items())),
        "hardware_behavior_file_count": classifications["HARDWARE_BEHAVIOR"] + classifications["MIXED_HARDWARE_SUPPORT"],
        "source_hashes_rechecked": True,
        "declaration_counter_exact": True,
        "phase": "SOURCE_FIRST_BULK_REWRITE_EXPORT_ONLY",
        "files": rows,
        "python_files": python_rows,
        "review_findings": [
            {"path": row["path"], "finding": finding}
            for row in rows for finding in row.get("review_findings", [])
        ],
        "coverage_complete": True,
        "implementation_complete": False,
        "behavior_validation_status": "DEFERRED_UNTIL_COMPLETE_SOURCE_COVERAGE",
        "acceptance_eligible": False,
    }


def main() -> int:
    payload = build_fragment()
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    summary = {key: payload[key] for key in (
        "source_file_count", "scala_line_count", "class_object_trait_declaration_count",
        "locked_module_definition_count", "classification_counts", "hardware_behavior_file_count",
    )}
    summary["python_owner_file_count"] = len(payload["python_files"])
    summary["existing_python_owner_count"] = sum(row["existing"] for row in payload["python_files"])
    summary["new_python_owner_count"] = sum(not row["existing"] for row in payload["python_files"])
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
