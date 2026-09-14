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
from typing import Any, Iterable

from amaranth import ClockDomain, ClockSignal, Elaboratable, Module, Mux, ResetSignal, Signal
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
    "full_backend_port_schema",
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


# Load the exact locked Backend port names and widths. / 加载锁定 Backend 端口名称与位宽。
def full_backend_port_schema() -> tuple[tuple[str, str, int], ...]:
    """Return the deterministic 1165-port Backend schema. / 返回确定性的 1165 端口 Backend 模式。"""
    root = Path(__file__).resolve().parents[6]
    path = root / "validation" / "backend-port-specs.json"
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = tuple((str(item["direction"]), str(item["name"]), int(item["width"]))
                         for item in payload.get("ports", []))
            if len(rows) == BACKEND_REFERENCE_PORT_COUNT:
                return rows
        except (OSError, ValueError, TypeError, KeyError):
            pass
    # Standalone fallback keeps geometry deterministic but intentionally does
    # not claim semantic correspondence to the locked names.
    rows: list[tuple[str, str, int]] = [("input", "clock", 1), ("input", "reset", 1)]
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
        existing_names = {signal.name for value in vars(self).values()
                          for signal in (value if isinstance(value, list) else [value])
                          if hasattr(signal, "name")}
        self.locked_ports: list[tuple[str, Signal]] = []
        for direction, name, width in self.locked_port_specs:
            signal = next((value for value in vars(self).values()
                           for value in (value if isinstance(value, list) else [value])
                           if getattr(value, "name", None) == name), None)
            if signal is None:
                signal = Signal(width, name=name)
                setattr(self, f"locked_{name}", signal)
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
            lane_exception = self.frontend_exception[lane * cfg.exception_width:(lane + 1) * cfg.exception_width].any()
            exception_any = exception_any | (lane_valid & lane_exception)
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
            for child_attr, parent_signal in (("flush", self.flush),):
                child_signal = getattr(self.datapath, child_attr, None)
                if child_signal is not None:
                    module.d.comb += child_signal.eq(parent_signal)
        if self.writeback is not None:
            module.submodules.writeback = self.writeback
            child_flush = getattr(self.writeback, "flush", None)
            if child_flush is not None:
                module.d.comb += child_flush.eq(self.flush)

        # Locked output ports are explicit tie-offs until their corresponding
        # Decode/Issue/Rename/CSR/EXU child closures are implemented.
        for direction, signal in self.locked_ports:
            if direction == "output" and signal.name not in {
                "io_toTop_cpuHalted", "io_toTop_cpuCriticalError", "io_toTop_msiAck",
                "io_fenceio_fencei", "io_fenceio_sbuffer_flushSb",
            }:
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
    name = str(config.get("name", config.get("module", "UHSCBackendTop")))
    return verilog.convert(top, name=name, ports=ports)


# Emit the exact 1165-port locked Backend envelope with deterministic ties.
# 以确定性 tie-off 导出锁定的精确 1165 端口 Backend 包络。
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
