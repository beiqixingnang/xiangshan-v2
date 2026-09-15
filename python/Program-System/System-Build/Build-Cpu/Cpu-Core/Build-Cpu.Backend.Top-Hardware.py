"""UHSC Kunminghu V2 backend parent boundary.
昆明湖 V2 后端父级边界的 UHSC Amaranth 实现。

The file is a搬运-ready parent boundary, not a claim that the 1165-port
generated ``Backend`` closure is already complete.  It keeps the observable
transaction rules at the parent boundary explicit and receives unfinished
children through constructor injection.  The locked Scala/SV provenance and
the reduced-closure status are recorded by the companion validator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, cast

from amaranth import ClockDomain, ClockSignal, Const, Elaboratable, Module, Mux, ResetSignal, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# Backend.scala instantiates control, scheduler, datapath, execution-unit, and
# writeback closures.  This boundary preserves the parent-visible ordering:
# six frontend lanes enter a one-entry dispatch register, flush cancels that
# register, and writeback arbitration chooses the lowest-priority live EXU per
# register-file port.  Unimplemented children are explicit injection points.
# Backend.scala 实例化控制、调度、数据通路、执行单元和写回闭包。本边界保留父级
# 可见顺序：六条前端通道进入一级 dispatch 寄存器，flush 清除该寄存器；写回仲裁
# 对每个寄存器文件端口选择优先级最低的有效 EXU。未实现子级必须显式注入。
__all__ = [
    "BackendTopConfig",
    "BackendTop",
    "UHSCCoreBackend",
    "BackendParent",
    "BackendFullTop",
    "BACKEND_PARENT_SOURCE_PATHS",
    "backend_parent_contract",
    "full_backend_port_schema",
    "backend_decode_pattern_model",
    "backend_parent_model",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class BackendTopConfig:
    """Explicit geometry for the reduced V2 parent boundary. / 精确配置 V2 父边界几何。"""

    fetch_width: int = 6
    exu_count: int = 8
    wb_port_count: int = 5
    instruction_width: int = 32
    pc_width: int = 50
    exception_width: int = 24
    data_width: int = 64
    pdest_width: int = 8
    queue_depth: int = 1
    # Opt-in export of the locked 1165-port parent envelope. / 显式启用锁定 1165 端口父包络导出。
    full_inventory: bool = False

    # Validate the V2 geometry and reject silent shape changes. / 校验 V2 几何并拒绝静默形状改变。
    def __post_init__(self) -> None:
        if self.fetch_width != 6:
            raise ValueError("Kunminghu V2 dispatch width is six")
        if self.exu_count < 1 or self.exu_count > 32:
            raise ValueError("exu_count must be in the supported 1..32 range")
        if self.wb_port_count != 5:
            raise ValueError("V2 WbDataPath exposes five register-file classes")
        for name in ("instruction_width", "pc_width", "exception_width", "data_width", "pdest_width"):
            if int(getattr(self, name)) < 1:
                raise ValueError(f"{name} must be positive")
        if self.queue_depth != 1:
            raise ValueError("the reduced parent boundary models one dispatch register")


# =============================================================================
# Locked Port Schema
# =============================================================================
# The generated V2 Backend header is an externally pinned contract.  The
# schema is loaded from the versioned validation artifact when available and
# falls back to deterministic placeholders for搬运-ready standalone use.
BACKEND_REFERENCE_PORT_COUNT = 1165
BACKEND_REFERENCE_INPUT_COUNT = 478
BACKEND_REFERENCE_OUTPUT_COUNT = 687

# Frozen V2 sources that form the executable Backend parent aggregate. /
# 构成可执行 Backend 父级聚合的冻结 V2 源路径。
#
# These paths are deliberately the seven source-evidence entries from the
# parent-closure readiness inventory.  They cover the parent, datapath,
# writeback, and decode boundaries without pretending that every inlined
# backend child is already behaviorally rewritten.
BACKEND_PARENT_SOURCE_PATHS: tuple[str, ...] = (
    "upstream/src/main/scala/xiangshan/backend/Backend.scala",
    "upstream/src/main/scala/xiangshan/backend/datapath/DataPath.scala",
    "upstream/src/main/scala/xiangshan/backend/datapath/DataSource.scala",
    "upstream/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala",
    "upstream/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala",
    "upstream/src/main/scala/xiangshan/backend/decode/DecodeUnit.scala",
    "upstream/src/main/scala/xiangshan/backend/decode/DecodeStage.scala",
    "upstream/src/main/scala/xiangshan/backend/issue/IssueQueue.scala",
    "upstream/src/main/scala/xiangshan/backend/issue/EnqPolicy.scala",
    "upstream/src/main/scala/xiangshan/backend/issue/AgeDetector.scala",
    "upstream/src/main/scala/xiangshan/backend/issue/FuBusyTableRead.scala",
    "upstream/src/main/scala/xiangshan/backend/exu/ExuBlock.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/Alu.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/Branch.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/Jump.scala",
)

# The DecodeUnit leaf patterns are kept local so the parent remains import
# free and can still elaborate when a caller does not inject a child module.
# DecodeUnit 叶级模式在父模块内保持本地化，确保无注入子模块时仍可独立展开。
BACKEND_DECODE_PATTERN_STRINGS: tuple[str, ...] = (
    "b000001???????????000?????1010111",
    "b000001???????????100?????1010111",
    "b010010??????01010010?????1010111",
    "b010010??????01000010?????1010111",
    "b010010??????01001010?????1010111",
    "b010010??????01100010?????1010111",
    "b010010??????01101010?????1010111",
    "b010010??????01110010?????1010111",
    "b010101???????????000?????1010111",
    "b010101???????????100?????1010111",
    "b01010????????????011?????1010111",
    "b010100???????????000?????1010111",
    "b010100???????????100?????1010111",
    "b110101???????????011?????1010111",
    "b110101???????????000?????1010111",
    "b110101???????????100?????1010111",
    "b1?00??0111???????100?????1110011",
    "b1?00??1??????????100?????1110011",
)


# Convert one Chisel-style BitPat into a hardware mask and expected value. /
# 将一个 Chisel 风格 BitPat 转换为硬件掩码和期望值。/
def _backend_pattern_mask_expected(pattern: str) -> tuple[int, int]:
    """Return a 32-bit ``(mask, expected)`` pair for a parent decoder pattern. /
    返回父级解码器模式的 32 位 ``(mask, expected)`` 对。
    """

    bits = pattern[1:] if pattern.startswith("b") else pattern
    bits = bits.rjust(32, "?")
    mask = 0
    expected = 0
    for bit in bits:
        mask = (mask << 1) | int(bit != "?")
        expected = (expected << 1) | (int(bit) if bit != "?" else 0)
    return mask, expected


BACKEND_DECODE_PATTERN_MASKS: tuple[tuple[int, int], ...] = tuple(
    _backend_pattern_mask_expected(pattern) for pattern in BACKEND_DECODE_PATTERN_STRINGS
)


# Evaluate the parent-local DecodeUnit pattern vector in Python. /
# 在 Python 中计算父级本地 DecodeUnit 模式向量。/
def backend_decode_pattern_model(instruction: int) -> int:
    """Return one bit per V2 DecodeUnit BitPat match. / 返回每个 V2 DecodeUnit BitPat 匹配的一位。"""

    value = int(instruction) & 0xFFFFFFFF
    result = 0
    for index, (mask, expected) in enumerate(BACKEND_DECODE_PATTERN_MASKS):
        if value & mask == expected:
            result |= 1 << index
    return result

# Return the machine-readable parent contract consumed by landing evidence. /
# 返回落地证据使用的机器可读父级契约。/
def backend_parent_contract() -> dict[str, Any]:
    """Describe the Backend aggregate and its intentionally open child gates. / 描述 Backend 聚合及明确保持开放的子级门禁。"""
    return {
        "closure_root": "core.backend.parent",
        "root_module": "Backend",
        "source_paths": list(BACKEND_PARENT_SOURCE_PATHS),
        "covered_children": [
            "DataPath",
            "DataSource",
            "NewPipelineConnect",
            "WbArbiter/WbDataPath",
            "DecodeUnit",
            "DecodeStage",
            "IssueQueue/EnqPolicy/AgeDetector/FuBusyTableRead",
            "ExuBlock/Alu/Branch/Jump",
        ],
        "observation_points": [
            "frontend-to-backend ready/valid",
            "dispatch register and flush",
            "EXU writeback class/port arbitration",
            "decode and issue child attachment status",
            "redirect and exception propagation",
        ],
        "port_envelope": {
            "reduced": 134,
            "locked": BACKEND_REFERENCE_PORT_COUNT,
            "locked_inputs": BACKEND_REFERENCE_INPUT_COUNT,
            "locked_outputs": BACKEND_REFERENCE_OUTPUT_COUNT,
        },
        "status": "STRUCTURE_AND_BOUNDARY_BEHAVIOR_LANDED",
        "behavior_scope": "decode-pattern, issue-slot, writeback-observation equations are active without injection; full queue/EXU closure remains pending",
        "accepted": False,
    }


# Load the exact locked Backend port names and widths. / 加载锁定 Backend 端口名称与位宽。
def full_backend_port_schema() -> tuple[tuple[str, str, int], ...]:
    """Return the deterministic 1165-port Backend schema. / 返回确定性的 1165 端口 Backend 模式。"""
    root = Path(__file__).resolve().parents[5]
    path = root / "validation" / "backend-port-specs.json"
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows: Any = tuple((str(item["direction"]), str(item["name"]), int(item["width"]))
                         for item in payload.get("ports", []))
            if len(rows) == BACKEND_REFERENCE_PORT_COUNT:
                return rows
        except (OSError, ValueError, TypeError, KeyError):
            pass
    # Standalone fallback keeps geometry deterministic but intentionally does
    # not claim semantic correspondence to the locked names.
    rows: Any = [("input", "clock", 1), ("input", "reset", 1)]
    rows.extend(("input", f"backend_inventory_input_{index:03d}", 1)
                for index in range(BACKEND_REFERENCE_INPUT_COUNT - 2))
    rows.extend(("output", f"backend_inventory_output_{index:03d}", 1)
                for index in range(BACKEND_REFERENCE_OUTPUT_COUNT))
    return tuple(rows)


# =============================================================================
# Implementation
# =============================================================================
class BackendTop(Elaboratable):
    """Reduced executable Backend parent closure. / 可执行的精简 Backend 父级闭包。"""

    # Construct parent-visible frontend, EXU, writeback, and redirect ports. / 构造父级可见前端、EXU、写回和重定向端口。
    def __init__(
        self,
        configuration: BackendTopConfig | dict[str, Any] | None = None,
        injected_dependencies: Any = None,
    ) -> None:
        if configuration is None:
            self.config = BackendTopConfig()
        elif isinstance(configuration, BackendTopConfig):
            self.config = configuration
        else:
            self.config = BackendTopConfig(**dict(configuration))
        self.injected_dependencies = injected_dependencies
        cfg = self.config
        fw = cfg.fetch_width
        exu = cfg.exu_count
        ports = cfg.wb_port_count

        # Clock/reset and parent control inputs. / 时钟、复位及父级控制输入。
        self.clock = ClockSignal("sync")
        self.reset = Signal(name="reset")
        self.flush = Signal(name="io_flush_valid")
        self.backend_can_accept = Signal(name="io_backendCanAccept")
        self.hart_id = Signal(6, name="io_fromTop_hartId")
        self.external_interrupt = Signal(7, name="io_fromTop_externalInterrupt")
        self.msi_valid = Signal(name="io_fromTop_msiInfo_valid")
        self.msi_bits = Signal(12, name="io_fromTop_msiInfo_bits")
        self.clint_time_valid = Signal(name="io_fromTop_clintTime_valid")
        self.clint_time = Signal(64, name="io_fromTop_clintTime_bits")

        # Six-wide frontend control-flow vector, flattened for a stable adapter.
        # 六宽前端控制流向量，展平以获得稳定适配器。
        self.frontend_valid = Signal(fw, name="io_frontend_cfVec_valid")
        self.frontend_instr = Signal(fw * cfg.instruction_width, name="io_frontend_cfVec_instr")
        self.frontend_exception = Signal(fw * cfg.exception_width, name="io_frontend_cfVec_exceptionVec")
        self.frontend_pc = Signal(fw * cfg.pc_width, name="io_frontend_cfVec_pc")
        self.frontend_ftq_ptr = Signal(fw * 6, name="io_frontend_cfVec_ftqPtr")
        self.frontend_ftq_offset = Signal(fw * 4, name="io_frontend_cfVec_ftqOffset")
        self.frontend_ready = Signal(fw, name="io_frontend_cfVec_ready")

        # Flattened EXU result channels.  Class 0..4 means int/fp/vf/v0/vl;
        # class 7 denotes no register-file write. / 展平 EXU 结果通道；类别 0..4
        # 分别表示 int/fp/vf/v0/vl，类别 7 表示不写寄存器文件。
        self.exu_valid = [Signal(name=f"io_fromExu_{i}_valid") for i in range(exu)]
        self.exu_ready = [Signal(name=f"io_fromExu_{i}_ready") for i in range(exu)]
        self.exu_data = [Signal(cfg.data_width, name=f"io_fromExu_{i}_data") for i in range(exu)]
        self.exu_pdest = [Signal(cfg.pdest_width, name=f"io_fromExu_{i}_pdest") for i in range(exu)]
        self.exu_class = [Signal(3, name=f"io_fromExu_{i}_rfClass") for i in range(exu)]
        self.exu_port = [Signal(max(1, (ports - 1).bit_length()), name=f"io_fromExu_{i}_wbPort") for i in range(exu)]
        self.exu_uncertain = [Signal(name=f"io_fromExu_{i}_uncertainLatency") for i in range(exu)]
        self.exu_no_data = [Signal(name=f"io_fromExu_{i}_hasNoDataWB") for i in range(exu)]
        self.exu_redirect = [Signal(name=f"io_fromExu_{i}_redirect") for i in range(exu)]
        self.wb_ready = [Signal(name=f"io_wb_{i}_ready") for i in range(ports)]

        # Parent outputs and observation points. / 父级输出及观测点。
        self.dispatch_valid = Signal(fw, name="io_toDispatch_valid")
        self.dispatch_instr = Signal(fw * cfg.instruction_width, name="io_toDispatch_instr")
        self.dispatch_exception = Signal(fw * cfg.exception_width, name="io_toDispatch_exceptionVec")
        self.dispatch_pc = Signal(fw * cfg.pc_width, name="io_toDispatch_pc")
        self.wb_valid = [Signal(name=f"io_toPreg_{i}_valid") for i in range(ports)]
        self.wb_data = [Signal(cfg.data_width, name=f"io_toPreg_{i}_data") for i in range(ports)]
        self.wb_pdest = [Signal(cfg.pdest_width, name=f"io_toPreg_{i}_pdest") for i in range(ports)]
        self.wb_class = [Signal(3, name=f"io_toPreg_{i}_rfClass") for i in range(ports)]
        self.wb_fire = [Signal(name=f"io_toPreg_{i}_fire") for i in range(ports)]
        self.frontend_can_accept = Signal(name="io_frontend_canAccept")
        self.redirect_valid = Signal(name="io_frontend_toFtq_redirect_valid")
        self.redirect_pc = Signal(cfg.pc_width, name="io_frontend_toFtq_redirect_pc")
        self.redirect_ftq_ptr = Signal(6, name="io_frontend_toFtq_redirect_ftqIdx")
        self.redirect_ftq_offset = Signal(4, name="io_frontend_toFtq_redirect_ftqOffset")
        self.cpu_halted = Signal(name="io_toTop_cpuHalted")
        self.cpu_critical_error = Signal(name="io_toTop_cpuCriticalError")
        self.msi_ack = Signal(name="io_toTop_msiAck")
        self.fencei = Signal(name="io_fenceio_fencei")
        self.sbuffer_flush = Signal(name="io_fenceio_sbuffer_flushSb")
        self.frontend_reset = Signal(name="io_frontendReset")

        # -----------------------------------------------------------------
        # Explicit vector/ROB/CSR ready-valid boundaries.  Backend.scala
        # carries these channels through several optional children; keeping
        # one-entry buffers here makes the parent contract executable even
        # when those children are not injected.  The aliases below retain a
        # compact Python-facing spelling while the generated names stay
        # stable and self-describing.
        # -----------------------------------------------------------------
        self.vector_in_valid = Signal(name="io_vector_in_valid")
        self.vector_in_ready = Signal(name="io_vector_in_ready")
        self.vector_in_bits = Signal(cfg.data_width, name="io_vector_in_bits")
        self.vector_out_valid = Signal(name="io_vector_out_valid")
        self.vector_out_ready = Signal(name="io_vector_out_ready")
        self.vector_out_bits = Signal(cfg.data_width, name="io_vector_out_bits")
        self.vector_flush = Signal(name="io_vector_flush")
        self.vector_flush_state = Signal(2, name="io_vector_flush_state")
        self.vector_valid = self.vector_in_valid
        self.vector_ready = self.vector_in_ready

        self.rob_in_valid = Signal(name="io_rob_in_valid")
        self.rob_in_ready = Signal(name="io_rob_in_ready")
        self.rob_in_bits = Signal(cfg.data_width, name="io_rob_in_bits")
        self.rob_out_valid = Signal(name="io_rob_out_valid")
        self.rob_out_ready = Signal(name="io_rob_out_ready")
        self.rob_out_bits = Signal(cfg.data_width, name="io_rob_out_bits")
        self.rob_flush = Signal(name="io_rob_flush")
        self.rob_flush_state = Signal(2, name="io_rob_flush_state")
        self.rob_valid = self.rob_in_valid
        self.rob_ready = self.rob_in_ready

        self.csr_req_valid = Signal(name="io_csr_req_valid")
        self.csr_req_ready = Signal(name="io_csr_req_ready")
        self.csr_req_write = Signal(name="io_csr_req_write")
        self.csr_req_addr = Signal(12, name="io_csr_req_addr")
        self.csr_req_data = Signal(cfg.data_width, name="io_csr_req_data")
        self.csr_resp_valid = Signal(name="io_csr_resp_valid")
        self.csr_resp_ready = Signal(name="io_csr_resp_ready")
        self.csr_resp_data = Signal(cfg.data_width, name="io_csr_resp_data")
        self.csr_flush = Signal(name="io_csr_flush")
        self.csr_flush_state = Signal(2, name="io_csr_flush_state")
        self.csr_valid = self.csr_req_valid
        self.csr_ready = self.csr_req_ready
        self.csr_rvalid = self.csr_resp_valid
        self.csr_rready = self.csr_resp_ready
        self.csr_rdata = self.csr_resp_data
        self.ready_valid_flush = Signal(name="io_readyValid_flush")

        # Reusable child-boundary observation signals.  These make Decode,
        # Issue, and Writeback attachment visible in generated RTL while
        # preserving the bounded parent contract and acceptance gate.
        self.child_decode_active = Signal(name="io_child_decode_active")
        self.child_decode_instruction = Signal(32, name="io_child_decode_instruction")
        self.child_decode_matches = Signal(32, name="io_child_decode_matches")
        self.child_issue_active = Signal(name="io_child_issue_active")
        self.child_issue_free_slots = Signal(22, name="io_child_issue_freeSlots")
        self.child_issue_can_enq = Signal(22, name="io_child_issue_canEnq")
        self.child_issue_selected_valid = Signal(name="io_child_issue_selected_valid")
        self.child_issue_selected_bits = Signal(22, name="io_child_issue_selected_bits")
        self.child_datapath_active = Signal(name="io_child_datapath_active")
        self.child_writeback_active = Signal(name="io_child_writeback_active")
        self.child_writeback_valid = [Signal(name=f"io_child_writeback_{i}_valid") for i in range(5)]
        self.child_writeback_data = [Signal(cfg.data_width, name=f"io_child_writeback_{i}_data") for i in range(5)]
        self.child_writeback_pdest = [Signal(cfg.pdest_width, name=f"io_child_writeback_{i}_pdest") for i in range(5)]

        # Explicit child closure injection points.  Existing leaf/family
        # implementations are connected by attribute contract when supplied;
        # absent children remain deterministic tie-offs in this parent.
        dependencies = injected_dependencies if isinstance(injected_dependencies, dict) else {}
        self.datapath = dependencies.get("datapath") or dependencies.get("DataPath")
        self.writeback = dependencies.get("writeback") or dependencies.get("WbDataPath")
        self.decode = dependencies.get("decode") or dependencies.get("DecodeUnit")
        self.issue = dependencies.get("issue") or dependencies.get("IssueQueue")

        # Materialize every locked Backend port as a stable signal.  The
        # bounded adapter below exports only its executable 134-port surface;
        # ``build_full_verilog`` exports this exact 1165-port envelope.
        self.locked_port_specs = full_backend_port_schema()
        self._locked_new_ids: set[int] = set()
        existing_names = {signal.name for value in vars(self).values()
                          for signal in (value if isinstance(value, list) else [value])
                          if hasattr(signal, "name")}
        self.locked_ports: list[tuple[str, Signal]] = []
        for direction, name, width in self.locked_port_specs:
            # ClockSignal("sync") is intentionally kept for the reduced
            # simulator contract; the locked ANSI header uses a distinct
            # externally named ``clock`` input.
            if name == "clock":
                signal = Signal(width, name="clock")
                setattr(self, "locked_clock", signal)
                self.locked_ports.append((direction, signal))
                continue
            signal = next((value for value in vars(self).values()
                           for value in (value if isinstance(value, list) else [value])
                           if getattr(value, "name", None) == name), None)
            if signal is None:
                signal = Signal(width, name=name)
                setattr(self, f"locked_{name}", signal)
                self._locked_new_ids.add(id(signal))
            self.locked_ports.append((direction, signal))

    # Elaborate the explicit dispatch register and five-class writeback network. / 展开显式 dispatch 寄存器及五类写回网络。
    def elaborate(self, platform) -> Module:
        del platform
        cfg = self.config
        fw = cfg.fetch_width
        exu_count = cfg.exu_count
        wb_count = cfg.wb_port_count
        module = Module()
        module.domains.sync = ClockDomain(async_reset=True)
        module.d.comb += ResetSignal("sync").eq(self.reset)

        # Frontend acceptance is gated by the parent admission signal and by a
        # full dispatch register.  Same-cycle retirement permits replacement.
        # 前端接收由父级准入和 dispatch 寄存器满状态共同控制；同周期退休可替换。
        register_empty = ~self.dispatch_valid.any()
        # Reduce the vector before combining it with the scalar admission
        # signal; this avoids width-dependent reduction behavior in simulators.
        # 先归约向量再与标量准入信号组合，避免仿真器中的位宽相关归约行为。
        dispatch_fire_any = self.dispatch_valid.any() & self.backend_can_accept
        accept_window = self.backend_can_accept & (register_empty | dispatch_fire_any) & ~self.flush
        module.d.comb += [
            self.frontend_can_accept.eq(accept_window),
            self.frontend_ready.eq(Mux(accept_window, self.frontend_valid, 0)),
            self.frontend_reset.eq(self.reset),
        ]
        accepted = self.frontend_valid & self.frontend_ready
        module.d.sync += [
            self.dispatch_valid.eq(Mux(self.flush, 0, Mux(accept_window, accepted, self.dispatch_valid))),
            self.dispatch_instr.eq(Mux(accept_window, self.frontend_instr, self.dispatch_instr)),
            self.dispatch_exception.eq(Mux(accept_window, self.frontend_exception, self.dispatch_exception)),
            self.dispatch_pc.eq(Mux(accept_window, self.frontend_pc, self.dispatch_pc)),
        ]

        # -----------------------------------------------------------------
        # Vector, ROB and CSR one-entry ready/valid channels.
        #
        # A channel accepts a beat when ``valid && ready`` and keeps its
        # payload stable until the consumer raises ``ready``.  A flush has
        # priority over every transfer: pending payloads are discarded and
        # output valid is held low for the flush state and one drain cycle.
        # This mirrors the parent-level redirect ordering without requiring
        # any child implementation or changing existing frontend/EXU ports.
        # -----------------------------------------------------------------
        flush_request = self.flush | self.vector_flush | self.rob_flush | self.csr_flush
        flush_state = Signal(2, init=0, name="backend_flush_state")
        FLUSH_IDLE = 0
        FLUSH_ACTIVE = 1
        FLUSH_DRAIN = 2
        flush_active = Signal(name="backend_flush_active")
        module.d.comb += flush_active.eq(flush_request | (flush_state != FLUSH_IDLE))
        module.d.comb += self.ready_valid_flush.eq(flush_active)
        module.d.sync += [
            # ACTIVE records the request; DRAIN guarantees a full cycle in
            # which no channel can observe stale valid data.
            flush_state.eq(Mux(flush_request, FLUSH_ACTIVE,
                               Mux(flush_state == FLUSH_ACTIVE, FLUSH_DRAIN, FLUSH_IDLE))),
        ]

        vector_pending = Signal(name="vector_pending")
        vector_payload = Signal(cfg.data_width, name="vector_payload")
        vector_space = ~vector_pending | (self.vector_out_ready & vector_pending)
        vector_fire_in = self.vector_in_valid & self.vector_in_ready
        vector_fire_out = self.vector_out_valid & self.vector_out_ready
        module.d.comb += [
            self.vector_in_ready.eq(vector_space & ~flush_active),
            self.vector_out_valid.eq(vector_pending & ~flush_active),
            self.vector_out_bits.eq(vector_payload),
            self.vector_flush_state.eq(Mux(flush_state == FLUSH_IDLE, 0,
                                           Mux(flush_state == FLUSH_ACTIVE, 1, 2))),
        ]
        module.d.sync += [
            vector_pending.eq(Mux(flush_active, 0,
                                  Mux(vector_fire_in, 1,
                                      Mux(vector_fire_out, 0, vector_pending)))),
            vector_payload.eq(Mux(vector_fire_in, self.vector_in_bits, vector_payload)),
        ]

        rob_pending = Signal(name="rob_pending")
        rob_payload = Signal(cfg.data_width, name="rob_payload")
        rob_space = ~rob_pending | (self.rob_out_ready & rob_pending)
        rob_fire_in = self.rob_in_valid & self.rob_in_ready
        rob_fire_out = self.rob_out_valid & self.rob_out_ready
        module.d.comb += [
            self.rob_in_ready.eq(rob_space & ~flush_active),
            self.rob_out_valid.eq(rob_pending & ~flush_active),
            self.rob_out_bits.eq(rob_payload),
            self.rob_flush_state.eq(Mux(flush_state == FLUSH_IDLE, 0,
                                        Mux(flush_state == FLUSH_ACTIVE, 1, 2))),
        ]
        module.d.sync += [
            rob_pending.eq(Mux(flush_active, 0,
                               Mux(rob_fire_in, 1,
                                   Mux(rob_fire_out, 0, rob_pending)))),
            rob_payload.eq(Mux(rob_fire_in, self.rob_in_bits, rob_payload)),
        ]

        # CSR requests use a shadow register for deterministic readback.  A
        # write is acknowledged with the written value; a read returns the
        # previous value.  The response remains valid under backpressure and
        # is cancelled by the same flush boundary as vector/ROB traffic.
        csr_shadow = Signal(cfg.data_width, init=0, name="csr_shadow")
        csr_resp_pending = Signal(name="csr_resp_pending")
        csr_resp_payload = Signal(cfg.data_width, name="csr_resp_payload")
        csr_space = ~csr_resp_pending | (self.csr_resp_ready & csr_resp_pending)
        csr_fire_in = self.csr_req_valid & self.csr_req_ready
        csr_fire_out = self.csr_resp_valid & self.csr_resp_ready
        module.d.comb += [
            self.csr_req_ready.eq(csr_space & ~flush_active),
            self.csr_resp_valid.eq(csr_resp_pending & ~flush_active),
            self.csr_resp_data.eq(csr_resp_payload),
            self.csr_flush_state.eq(Mux(flush_state == FLUSH_IDLE, 0,
                                        Mux(flush_state == FLUSH_ACTIVE, 1, 2))),
        ]
        module.d.sync += [
            csr_resp_pending.eq(Mux(flush_active, 0,
                                    Mux(csr_fire_in, 1,
                                        Mux(csr_fire_out, 0, csr_resp_pending)))),
            csr_resp_payload.eq(Mux(csr_fire_in,
                                     Mux(self.csr_req_write, self.csr_req_data, csr_shadow),
                                     csr_resp_payload)),
            csr_shadow.eq(Mux(flush_active, csr_shadow,
                              Mux(csr_fire_in & self.csr_req_write,
                                  self.csr_req_data, csr_shadow))),
        ]

        # Select the first live EXU for each V2 writeback class/port.  The
        # loop order is the deterministic priority order used by WbArbiter.
        # 对每个 V2 写回类别/端口选择首个有效 EXU；循环顺序即确定性优先级。
        for port_index in range(wb_count):
            chosen_valid: Any = 0
            chosen_index: Any = 0
            for exu_index in range(exu_count):
                matches = (
                    self.exu_valid[exu_index]
                    & ~self.flush
                    & (self.exu_class[exu_index] != 7)
                    & (self.exu_port[exu_index] == port_index)
                )
                take = matches & ~chosen_valid
                chosen_index = Mux(take, exu_index, chosen_index)
                chosen_valid = chosen_valid | matches
            # Dynamic Array indexing is synthesizable in Amaranth and emits a
            # priority mux matching the Scala arbiter's sorted input group.
            data_mux: Any = 0
            pdest_mux: Any = 0
            class_mux: Any = 7
            for exu_index in range(exu_count - 1, -1, -1):
                selected = chosen_index == exu_index
                data_mux = Mux(selected, self.exu_data[exu_index], data_mux)
                pdest_mux = Mux(selected, self.exu_pdest[exu_index], pdest_mux)
                class_mux = Mux(selected, self.exu_class[exu_index], class_mux)
            module.d.comb += [
                self.wb_valid[port_index].eq(chosen_valid),
                self.wb_data[port_index].eq(Mux(chosen_valid, data_mux, 0)),
                self.wb_pdest[port_index].eq(Mux(chosen_valid, pdest_mux, 0)),
                self.wb_class[port_index].eq(Mux(chosen_valid, class_mux, 7)),
                self.wb_fire[port_index].eq(chosen_valid & self.wb_ready[port_index]),
            ]

        # Each uncertain-latency EXU waits for its winning output; fixed-latency
        # and no-data units retain V2's always-ready contract.
        # 不确定延迟 EXU 等待其获胜写回端口；确定延迟和无数据单元始终 ready。
        for exu_index in range(exu_count):
            terms: list[Any] = []
            for port_index in range(wb_count):
                terms.append(
                    self.wb_fire[port_index]
                    & (self.exu_class[exu_index] != 7)
                    & (self.exu_port[exu_index] == port_index)
                    & self.exu_valid[exu_index]
                )
            selected_any: Any = 0
            for term in terms:
                selected_any = selected_any | term
            module.d.comb += self.exu_ready[exu_index].eq(
                (~self.exu_valid[exu_index])
                | self.exu_no_data[exu_index]
                | ~self.exu_uncertain[exu_index]
                | selected_any
            )

        # Redirect is raised by a flushed parent, an EXU redirect, or an input
        # exception.  Lowest frontend lane wins, preserving Vec/Seq ordering.
        # flush、EXU 重定向或前端异常均产生 redirect；最低前端 lane 优先。
        exception_any: Any = 0
        for lane in range(fw):
            lane_valid = self.frontend_valid[lane]
            lane_exception = 0
            for bit in self.frontend_exception[lane * cfg.exception_width:(lane + 1) * cfg.exception_width]:
                lane_exception = lane_exception | cast(Any, bit)
            exception_any = exception_any | (cast(Any, lane_valid) & lane_exception)
        exu_redirect_any: Any = 0
        for signal in self.exu_redirect:
            exu_redirect_any = exu_redirect_any | signal
        module.d.comb += [
            self.redirect_valid.eq(self.flush | exception_any | exu_redirect_any),
            self.cpu_critical_error.eq(exception_any),
            self.cpu_halted.eq(0),
            self.msi_ack.eq(self.msi_valid & ~self.reset),
            self.fencei.eq(self.flush),
            self.sbuffer_flush.eq(self.flush),
            self.redirect_pc.eq(self.frontend_pc[:cfg.pc_width]),
            self.redirect_ftq_ptr.eq(self.frontend_ftq_ptr[:6]),
            self.redirect_ftq_offset.eq(self.frontend_ftq_offset[:4]),
        ]

        # Bind optional datapath/writeback children at the parent boundary.
        # Connections are intentionally attribute-based so independent family
        # builds can be injected without imports or hidden global state.
        if self.datapath is not None:
            module.submodules.datapath = self.datapath
            # Make datapath injection visible at the parent boundary without
            # assuming a particular child port shape.
            # 在不假设子级端口形状的前提下，让数据通路注入在父边界可见。
            module.d.comb += self.child_datapath_active.eq(1)
            for child_attr, parent_signal in (("flush", self.flush),):
                child_signal = getattr(self.datapath, child_attr, None)
                if child_signal is not None:
                    module.d.comb += child_signal.eq(parent_signal)
        if self.writeback is not None:
            module.submodules.writeback = self.writeback
            child_flush = getattr(self.writeback, "flush", None)
            if child_flush is not None:
                module.d.comb += child_flush.eq(self.flush)
            # WbDataPath's existing reusable contract exposes flattened EXU
            # channels.  Attach matching lanes/classes when present, while
            # leaving a differently-shaped injected child untouched.
            wb_lanes = min(
                len(getattr(self.writeback, "fromExu_valid", ())),
                len(getattr(self.writeback, "fromExu_bits", ())),
                len(getattr(self.writeback, "fromExu_pdest", ())), exu_count,
            )
            for index in range(wb_lanes):
                module.d.comb += [
                    self.writeback.fromExu_valid[index].eq(self.exu_valid[index]),
                    self.writeback.fromExu_bits[index].eq(self.exu_data[index]),
                    self.writeback.fromExu_pdest[index].eq(self.exu_pdest[index]),
                ]
                for attr_name, class_index in (("toIntRf", 0), ("toFpRf", 1), ("toVecRf", 2),
                                               ("toV0Rf", 3), ("toVlRf", 4)):
                    signals = getattr(self.writeback, attr_name, ())
                    if index < len(signals):
                        module.d.comb += signals[index].eq(self.exu_class[index] == class_index)

        # The parent has a useful standalone boundary even without injected
        # children: DecodeUnit BitPat matches, EnqPolicy's low/high selector,
        # and WbDataPath observations are evaluated directly.  Injection keeps
        # precedence and is still supported for family-level closure tests.
        # 即使没有注入子模块，父边界也会直接计算 DecodeUnit BitPat 匹配、
        # EnqPolicy 低高选择和 WbDataPath 观测；注入时仍保持优先级。
        module.d.comb += self.child_decode_instruction.eq(self.frontend_instr[:32])
        module.d.comb += self.child_datapath_active.eq(1 if self.datapath is not None else 0)
        if self.decode is None:
            module.d.comb += self.child_decode_active.eq(1)
            match_value: Any = 0
            for bit_index, (mask, expected) in enumerate(BACKEND_DECODE_PATTERN_MASKS):
                matched = (self.child_decode_instruction & Const(mask, 32)) == Const(expected, 32)
                match_value = cast(Any, match_value) | (cast(Any, matched) << bit_index)
            module.d.comb += self.child_decode_matches.eq(match_value)
        else:
            module.d.comb += self.child_decode_active.eq(0)
            module.d.comb += self.child_decode_matches.eq(0)
        if self.issue is None:
            # CircSelectOne's first rank walks low-to-high.  The two's
            # complement expression is equivalent to priority encoding the
            # least-significant free issue slot.
            module.d.comb += [
                self.child_issue_active.eq(1),
                self.child_issue_can_enq.eq(self.child_issue_free_slots),
                self.child_issue_selected_valid.eq(self.child_issue_free_slots != 0),
                self.child_issue_selected_bits.eq(
                    self.child_issue_free_slots & (-self.child_issue_free_slots)
                ),
            ]
        else:
            module.d.comb += [
                self.child_issue_active.eq(0),
                self.child_issue_can_enq.eq(0),
                self.child_issue_selected_valid.eq(0),
                self.child_issue_selected_bits.eq(0),
            ]
        module.d.comb += self.child_writeback_active.eq(self.wb_valid[0] | self.wb_valid[1] |
                                                        self.wb_valid[2] | self.wb_valid[3] |
                                                        self.wb_valid[4])
        for index, signal in enumerate(self.child_writeback_valid):
            module.d.comb += signal.eq(self.wb_valid[index])
        for index, signal in enumerate(self.child_writeback_data):
            module.d.comb += signal.eq(self.wb_data[index])
        for index, signal in enumerate(self.child_writeback_pdest):
            module.d.comb += signal.eq(self.wb_pdest[index])
        if self.decode is not None:
            module.submodules.decode = self.decode
            child_instruction = getattr(self.decode, "instruction", None)
            child_matches = getattr(self.decode, "matches", None)
            if child_instruction is not None:
                module.d.comb += [self.child_decode_active.eq(1), child_instruction.eq(self.child_decode_instruction)]
                if isinstance(child_matches, dict):
                    for index, signal in enumerate(child_matches.values()):
                        if index >= 32:
                            break
                        module.d.comb += cast(Any, self.child_decode_matches[index]).eq(cast(Any, signal))
        if self.issue is not None:
            module.submodules.issue = self.issue
            child_can_enq = getattr(self.issue, "can_enq", None)
            if child_can_enq is not None:
                module.d.comb += [self.child_issue_active.eq(1), child_can_enq.eq(self.child_issue_free_slots),
                                  self.child_issue_can_enq.eq(child_can_enq)]
                selected_valid = getattr(self.issue, "selection_valid", None)
                selected_bits = getattr(self.issue, "selection_bits", None)
                if isinstance(selected_valid, (list, tuple)) and selected_valid:
                    module.d.comb += self.child_issue_selected_valid.eq(selected_valid[0])
                if isinstance(selected_bits, (list, tuple)) and selected_bits:
                    module.d.comb += self.child_issue_selected_bits.eq(selected_bits[0])
        if self.writeback is not None:
            valid_groups = [getattr(self.writeback, name, None) for name in (
                "toIntPreg_valid", "toFpPreg_valid", "toVfPreg_valid", "toV0Preg_valid", "toVlPreg_valid")]
            data_groups = [getattr(self.writeback, name, None) for name in (
                "toIntPreg_bits", "toFpPreg_bits", "toVfPreg_bits", "toV0Preg_bits", "toVlPreg_bits")]
            pdest_groups = [getattr(self.writeback, name, None) for name in (
                "toIntPreg_pdest", "toFpPreg_pdest", "toVfPreg_pdest", "toV0Preg_pdest", "toVlPreg_pdest")]
            if any(group is not None for group in (*valid_groups, *data_groups, *pdest_groups)):
                module.d.comb += self.child_writeback_active.eq(1)
                for index in range(5):
                    valid_group = valid_groups[index]
                    data_group = data_groups[index]
                    pdest_group = pdest_groups[index]
                    if isinstance(valid_group, (list, tuple)) and valid_group:
                        module.d.comb += self.child_writeback_valid[index].eq(valid_group[0])
                    if isinstance(data_group, (list, tuple)) and data_group:
                        module.d.comb += self.child_writeback_data[index].eq(data_group[0])
                    if isinstance(pdest_group, (list, tuple)) and pdest_group:
                        module.d.comb += self.child_writeback_pdest[index].eq(pdest_group[0])

        # Locked output ports are explicit tie-offs until their corresponding
        # Decode/Issue/Rename/CSR/EXU child closures are implemented.
        for direction, signal in self.locked_ports:
            # Only tie off newly-created envelope signals.  Existing
            # executable parent signals keep their reduced behavioral
            # equations, preventing the full envelope from overriding direct
            # validator observations.
            if direction == "output" and id(signal) in self._locked_new_ids:
                module.d.comb += signal.eq(0)
        return module


# Keep source-oriented aliases for internal closure callers. / 为内部闭包调用方保留源代码导向别名。
UHSCCoreBackend = BackendTop
BackendParent = BackendTop
BackendFullTop = BackendTop


# Compute the executable parent oracle used by direct and differential tests. / 计算 direct 与差分测试使用的父级可执行 oracle。
def backend_parent_model(
    frontend_valid: int,
    frontend_instr: Iterable[int],
    frontend_exception: Iterable[int],
    frontend_pc: Iterable[int],
    backend_can_accept: bool,
    flush: bool,
    exu_valid: Iterable[bool],
    exu_data: Iterable[int],
    exu_pdest: Iterable[int],
    exu_class: Iterable[int],
    exu_port: Iterable[int],
    wb_ready: Iterable[bool],
    exu_uncertain: Iterable[bool] | None = None,
    exu_no_data: Iterable[bool] | None = None,
    exu_redirect: Iterable[bool] | None = None,
    msi_valid: bool = False,
    reset: bool = False,
) -> dict[str, Any]:
    """Return one deterministic reduced-parent transaction result. / 返回一笔确定性的精简父级事务结果。"""
    valid = [bool(x) for x in exu_valid]
    data = [int(x) for x in exu_data]
    pdest = [int(x) for x in exu_pdest]
    classes = [int(x) for x in exu_class]
    ports = [int(x) for x in exu_port]
    ready = [bool(x) for x in wb_ready]
    uncertain = [bool(x) for x in (exu_uncertain or [False] * len(valid))]
    no_data = [bool(x) for x in (exu_no_data or [False] * len(valid))]
    redirects = [bool(x) for x in (exu_redirect or [False] * len(valid))]
    wb: list[dict[str, int]] = []
    for port_index in range(len(ready)):
        winner = next((index for index in range(len(valid))
                       if valid[index] and not flush and classes[index] != 7 and ports[index] == port_index), None)
        if winner is None:
            wb.append({"valid": 0, "data": 0, "pdest": 0, "class": 7, "fire": 0})
        else:
            wb.append({"valid": 1, "data": data[winner], "pdest": pdest[winner],
                       "class": classes[winner], "fire": int(ready[port_index])})
    exu_ready_result: list[int] = []
    for index, item_valid in enumerate(valid):
        selected = any(item["fire"] and item["valid"] and classes[index] != 7 and ports[index] == port_index
                       for port_index, item in enumerate(wb))
        exu_ready_result.append(int((not item_valid) or no_data[index] or not uncertain[index] or selected))
    exception = any(bool(frontend_valid & (1 << lane)) and bool(int(value))
                    for lane, value in enumerate(frontend_exception))
    redirect = bool(flush or exception or any(redirects))
    return {
        "frontend_can_accept": int(bool(backend_can_accept) and not bool(flush)),
        "frontend_ready": int(frontend_valid) if bool(backend_can_accept) and not bool(flush) else 0,
        "writeback": wb,
        "exu_ready": exu_ready_result,
        "redirect_valid": int(redirect),
        "cpu_critical_error": int(exception),
        "cpu_halted": 0,
        "msi_ack": int(bool(msi_valid) and not bool(reset)),
        "fencei": int(bool(flush)),
        "sbuffer_flush": int(bool(flush)),
    }


# =============================================================================
# Public Adapter
# =============================================================================
# Export the deterministic reduced V2 parent boundary. / 导出确定性的精简 V2 父级边界。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the configured Backend parent. / 返回配置 Backend 父级的 Verilog。"""
    # ``full_inventory`` is an explicit integration gate.  Existing callers
    # retain the bounded 134-port export unless they opt into the locked
    # Backend envelope.
    if isinstance(configuration, dict) and bool(configuration.get("full_inventory", False)):
        return build_full_verilog(configuration, injected_dependencies)
    del injected_dependencies
    config = configuration if isinstance(configuration, dict) else {}
    if isinstance(configuration, BackendTopConfig):
        cfg = configuration
    else:
        cfg = BackendTopConfig(**{
            key: value for key, value in config.items()
            if key in BackendTopConfig.__dataclass_fields__
        })
    top = BackendTop(cfg)
    ports: list[Any] = [
        top.clock, top.reset, top.flush, top.backend_can_accept, top.hart_id,
        top.external_interrupt, top.msi_valid, top.msi_bits, top.clint_time_valid,
        top.clint_time, top.frontend_valid, top.frontend_instr, top.frontend_exception,
        top.frontend_pc, top.frontend_ftq_ptr, top.frontend_ftq_offset, top.frontend_ready,
        top.dispatch_valid, top.dispatch_instr, top.dispatch_exception, top.dispatch_pc,
        top.frontend_can_accept, top.redirect_valid, top.redirect_pc,
        top.redirect_ftq_ptr, top.redirect_ftq_offset, top.cpu_halted,
        top.cpu_critical_error, top.msi_ack, top.fencei, top.sbuffer_flush,
        top.frontend_reset,
    ]
    ports += top.exu_valid + top.exu_ready + top.exu_data + top.exu_pdest
    ports += top.exu_class + top.exu_port + top.exu_uncertain + top.exu_no_data + top.exu_redirect
    ports += top.wb_ready + top.wb_valid + top.wb_data + top.wb_pdest + top.wb_class + top.wb_fire
    ports += [top.child_decode_active, top.child_decode_instruction, top.child_decode_matches,
              top.child_issue_active, top.child_issue_free_slots, top.child_issue_can_enq,
              top.child_issue_selected_valid, top.child_issue_selected_bits,
              top.child_datapath_active, top.child_writeback_active] + top.child_writeback_valid + top.child_writeback_data + top.child_writeback_pdest
    ports += [top.vector_in_valid, top.vector_in_ready, top.vector_in_bits,
              top.vector_out_valid, top.vector_out_ready, top.vector_out_bits,
              top.vector_flush, top.vector_flush_state,
              top.rob_in_valid, top.rob_in_ready, top.rob_in_bits,
              top.rob_out_valid, top.rob_out_ready, top.rob_out_bits,
              top.rob_flush, top.rob_flush_state,
              top.csr_req_valid, top.csr_req_ready, top.csr_req_write,
              top.csr_req_addr, top.csr_req_data, top.csr_resp_valid,
              top.csr_resp_ready, top.csr_resp_data, top.csr_flush,
              top.csr_flush_state, top.ready_valid_flush]
    name = str(config.get("name", config.get("module", "UHSCBackendTop")))
    return verilog.convert(top, name=name, ports=ports)


# Emit the exact 1165-port locked Backend envelope with deterministic ties.
# 以确定性 tie-off 导出锁定的精确 1165 端口 Backend 包络。 /
def build_full_verilog(configuration=None, injected_dependencies=None):
    """Return a full-inventory Backend RTL envelope.

    The envelope preserves all locked names and widths and binds available
    parent outputs; unimplemented child outputs remain tied low.  This is an
    inventory/structural gate, not behavioral acceptance of the full Backend.
    """
    options = dict(configuration) if isinstance(configuration, dict) else {}
    cfg_fields = BackendTopConfig.__dataclass_fields__
    cfg = BackendTopConfig(**{key: value for key, value in options.items() if key in cfg_fields})
    top = BackendTop(cfg, injected_dependencies)
    ports = [signal for _direction, signal in top.locked_ports]
    name = str(options.get("module", options.get("name", "UHSCBackend")))
    return verilog.convert(top, name=name, ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
# Print a deterministic default export for command-line smoke tests. / 为命令行 smoke 测试打印确定性默认导出。
def main() -> None:
    print(build_verilog(None, None))


if __name__ == "__main__":
    main()
