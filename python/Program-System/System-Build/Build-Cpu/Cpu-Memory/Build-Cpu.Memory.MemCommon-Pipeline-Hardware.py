"""UHSC V2 memory pipeline-register family.
昆明湖 V2 内存流水寄存器 family。

MemCommon.scala defines AddPipelineReg.PipelineRegModule once and
specializes it for several bundle shapes.  The generated hierarchy therefore
contains multiple numbered members with the same ready/valid state machine.
This aggregate keeps the bundle fields explicit while sharing one faithful
Decoupled register implementation.
"""

from __future__ import annotations

from typing import Any, cast

from amaranth import ClockDomain, Elaboratable, Module, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = ["COVERED_MODULES", "PipelineRegFamily", "build_verilog", "main"]

COVERED_MODULES: tuple[str, ...] = (
    "PipelineRegModule", "PipelineRegModule_1", "PipelineRegModule_2", "PipelineRegModule_6",
)


FIELD_LAYOUTS: dict[str, tuple[tuple[str, int], ...]] = {
    "PipelineRegModule": (
        ("robIdx_flag", 1), ("robIdx_value", 8), ("cmd", 5), ("addr", 48),
        ("vaddr", 50), ("data", 64), ("mask", 8), ("id", 7), ("nc", 1),
        ("memBackTypeMM", 1),
    ),
    "PipelineRegModule_1": (
        ("uop_exceptionVec_3", 1), ("uop_exceptionVec_4", 1), ("uop_exceptionVec_5", 1),
        ("uop_exceptionVec_13", 1), ("uop_exceptionVec_19", 1), ("uop_exceptionVec_21", 1),
        ("uop_trigger", 4), ("uop_preDecodeInfo_isRVC", 1), ("uop_ftqPtr_flag", 1),
        ("uop_ftqPtr_value", 6), ("uop_ftqOffset", 4), ("uop_fuOpType", 9),
        ("uop_rfWen", 1), ("uop_fpWen", 1), ("uop_flushPipe", 1),
        ("uop_vpu_vstart", 8), ("uop_vpu_veew", 2), ("uop_uopIdx", 7),
        ("uop_pdest", 8), ("uop_robIdx_flag", 1), ("uop_robIdx_value", 8),
        ("uop_storeSetHit", 1), ("uop_waitForRobIdx_flag", 1),
        ("uop_waitForRobIdx_value", 8), ("uop_loadWaitBit", 1),
        ("uop_loadWaitStrict", 1), ("uop_lqIdx_flag", 1), ("uop_lqIdx_value", 7),
        ("uop_sqIdx_flag", 1), ("uop_sqIdx_value", 6), ("uop_replayInst", 1),
    ),
    "PipelineRegModule_2": (
        ("uop_exceptionVec_4", 1), ("uop_exceptionVec_19", 1),
        ("uop_preDecodeInfo_isRVC", 1), ("uop_ftqPtr_flag", 1),
        ("uop_ftqPtr_value", 6), ("uop_ftqOffset", 4), ("uop_fuOpType", 9),
        ("uop_rfWen", 1), ("uop_fpWen", 1), ("uop_vpu_vstart", 8),
        ("uop_vpu_veew", 2), ("uop_uopIdx", 7), ("uop_pdest", 8),
        ("uop_robIdx_flag", 1), ("uop_robIdx_value", 8), ("uop_storeSetHit", 1),
        ("uop_waitForRobIdx_flag", 1), ("uop_waitForRobIdx_value", 8),
        ("uop_loadWaitBit", 1), ("uop_loadWaitStrict", 1), ("uop_lqIdx_flag", 1),
        ("uop_lqIdx_value", 7), ("uop_sqIdx_flag", 1), ("uop_sqIdx_value", 6),
        ("vaddr", 50), ("paddr", 48), ("data", 129), ("isvec", 1),
        ("is128bit", 1), ("vecActive", 1), ("schedIndex", 7),
    ),
    "PipelineRegModule_6": (
        ("data", 64), ("id", 4), ("nc", 1), ("is2lq", 1),
        ("denied", 1), ("corrupt", 1),
    ),
}


# =============================================================================
# Configuration
# =============================================================================
def port_specs(member: str) -> tuple[tuple[str, str, int], ...]:
    """Build the exact flattened ANSI port list. / 构造精确扁平 ANSI 端口表。"""

    fields = FIELD_LAYOUTS[member]
    ports: list[tuple[str, str, int]] = [
        ("clock", "input", 1), ("reset", "input", 1), ("io_in_ready", "output", 1),
        ("io_in_valid", "input", 1),
    ]
    ports.extend((f"io_in_bits_{name}", "input", width) for name, width in fields)
    ports.append(("io_out_ready", "input", 1))
    ports.append(("io_out_valid", "output", 1))
    ports.extend((f"io_out_bits_{name}", "output", width) for name, width in fields)
    return tuple(ports)


PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {
    member: port_specs(member) for member in COVERED_MODULES
}

PortSpec = tuple[str, str, int]

PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    'PipelineRegModule': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_in_ready', 'output', 1),
        ('io_in_valid', 'input', 1),
        ('io_in_bits_robIdx_flag', 'input', 1),
        ('io_in_bits_robIdx_value', 'input', 8),
        ('io_in_bits_cmd', 'input', 5),
        ('io_in_bits_addr', 'input', 48),
        ('io_in_bits_vaddr', 'input', 50),
        ('io_in_bits_data', 'input', 64),
        ('io_in_bits_mask', 'input', 8),
        ('io_in_bits_id', 'input', 7),
        ('io_in_bits_nc', 'input', 1),
        ('io_in_bits_memBackTypeMM', 'input', 1),
        ('io_out_ready', 'input', 1),
        ('io_out_valid', 'output', 1),
        ('io_out_bits_robIdx_flag', 'output', 1),
        ('io_out_bits_robIdx_value', 'output', 8),
        ('io_out_bits_cmd', 'output', 5),
        ('io_out_bits_addr', 'output', 48),
        ('io_out_bits_vaddr', 'output', 50),
        ('io_out_bits_data', 'output', 64),
        ('io_out_bits_mask', 'output', 8),
        ('io_out_bits_id', 'output', 7),
        ('io_out_bits_nc', 'output', 1),
        ('io_out_bits_memBackTypeMM', 'output', 1),
    ),
    'PipelineRegModule_1': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_in_ready', 'output', 1),
        ('io_in_valid', 'input', 1),
        ('io_in_bits_uop_exceptionVec_3', 'input', 1),
        ('io_in_bits_uop_exceptionVec_4', 'input', 1),
        ('io_in_bits_uop_exceptionVec_5', 'input', 1),
        ('io_in_bits_uop_exceptionVec_13', 'input', 1),
        ('io_in_bits_uop_exceptionVec_19', 'input', 1),
        ('io_in_bits_uop_exceptionVec_21', 'input', 1),
        ('io_in_bits_uop_trigger', 'input', 4),
        ('io_in_bits_uop_preDecodeInfo_isRVC', 'input', 1),
        ('io_in_bits_uop_ftqPtr_flag', 'input', 1),
        ('io_in_bits_uop_ftqPtr_value', 'input', 6),
        ('io_in_bits_uop_ftqOffset', 'input', 4),
        ('io_in_bits_uop_fuOpType', 'input', 9),
        ('io_in_bits_uop_rfWen', 'input', 1),
        ('io_in_bits_uop_fpWen', 'input', 1),
        ('io_in_bits_uop_flushPipe', 'input', 1),
        ('io_in_bits_uop_vpu_vstart', 'input', 8),
        ('io_in_bits_uop_vpu_veew', 'input', 2),
        ('io_in_bits_uop_uopIdx', 'input', 7),
        ('io_in_bits_uop_pdest', 'input', 8),
        ('io_in_bits_uop_robIdx_flag', 'input', 1),
        ('io_in_bits_uop_robIdx_value', 'input', 8),
        ('io_in_bits_uop_storeSetHit', 'input', 1),
        ('io_in_bits_uop_waitForRobIdx_flag', 'input', 1),
        ('io_in_bits_uop_waitForRobIdx_value', 'input', 8),
        ('io_in_bits_uop_loadWaitBit', 'input', 1),
        ('io_in_bits_uop_loadWaitStrict', 'input', 1),
        ('io_in_bits_uop_lqIdx_flag', 'input', 1),
        ('io_in_bits_uop_lqIdx_value', 'input', 7),
        ('io_in_bits_uop_sqIdx_flag', 'input', 1),
        ('io_in_bits_uop_sqIdx_value', 'input', 6),
        ('io_in_bits_uop_replayInst', 'input', 1),
        ('io_out_ready', 'input', 1),
        ('io_out_valid', 'output', 1),
        ('io_out_bits_uop_exceptionVec_3', 'output', 1),
        ('io_out_bits_uop_exceptionVec_4', 'output', 1),
        ('io_out_bits_uop_exceptionVec_5', 'output', 1),
        ('io_out_bits_uop_exceptionVec_13', 'output', 1),
        ('io_out_bits_uop_exceptionVec_19', 'output', 1),
        ('io_out_bits_uop_exceptionVec_21', 'output', 1),
        ('io_out_bits_uop_trigger', 'output', 4),
        ('io_out_bits_uop_preDecodeInfo_isRVC', 'output', 1),
        ('io_out_bits_uop_ftqPtr_flag', 'output', 1),
        ('io_out_bits_uop_ftqPtr_value', 'output', 6),
        ('io_out_bits_uop_ftqOffset', 'output', 4),
        ('io_out_bits_uop_fuOpType', 'output', 9),
        ('io_out_bits_uop_rfWen', 'output', 1),
        ('io_out_bits_uop_fpWen', 'output', 1),
        ('io_out_bits_uop_flushPipe', 'output', 1),
        ('io_out_bits_uop_vpu_vstart', 'output', 8),
        ('io_out_bits_uop_vpu_veew', 'output', 2),
        ('io_out_bits_uop_uopIdx', 'output', 7),
        ('io_out_bits_uop_pdest', 'output', 8),
        ('io_out_bits_uop_robIdx_flag', 'output', 1),
        ('io_out_bits_uop_robIdx_value', 'output', 8),
        ('io_out_bits_uop_storeSetHit', 'output', 1),
        ('io_out_bits_uop_waitForRobIdx_flag', 'output', 1),
        ('io_out_bits_uop_waitForRobIdx_value', 'output', 8),
        ('io_out_bits_uop_loadWaitBit', 'output', 1),
        ('io_out_bits_uop_loadWaitStrict', 'output', 1),
        ('io_out_bits_uop_lqIdx_flag', 'output', 1),
        ('io_out_bits_uop_lqIdx_value', 'output', 7),
        ('io_out_bits_uop_sqIdx_flag', 'output', 1),
        ('io_out_bits_uop_sqIdx_value', 'output', 6),
        ('io_out_bits_uop_replayInst', 'output', 1),
    ),
    'PipelineRegModule_2': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_in_ready', 'output', 1),
        ('io_in_valid', 'input', 1),
        ('io_in_bits_uop_exceptionVec_4', 'input', 1),
        ('io_in_bits_uop_exceptionVec_19', 'input', 1),
        ('io_in_bits_uop_preDecodeInfo_isRVC', 'input', 1),
        ('io_in_bits_uop_ftqPtr_flag', 'input', 1),
        ('io_in_bits_uop_ftqPtr_value', 'input', 6),
        ('io_in_bits_uop_ftqOffset', 'input', 4),
        ('io_in_bits_uop_fuOpType', 'input', 9),
        ('io_in_bits_uop_rfWen', 'input', 1),
        ('io_in_bits_uop_fpWen', 'input', 1),
        ('io_in_bits_uop_vpu_vstart', 'input', 8),
        ('io_in_bits_uop_vpu_veew', 'input', 2),
        ('io_in_bits_uop_uopIdx', 'input', 7),
        ('io_in_bits_uop_pdest', 'input', 8),
        ('io_in_bits_uop_robIdx_flag', 'input', 1),
        ('io_in_bits_uop_robIdx_value', 'input', 8),
        ('io_in_bits_uop_storeSetHit', 'input', 1),
        ('io_in_bits_uop_waitForRobIdx_flag', 'input', 1),
        ('io_in_bits_uop_waitForRobIdx_value', 'input', 8),
        ('io_in_bits_uop_loadWaitBit', 'input', 1),
        ('io_in_bits_uop_loadWaitStrict', 'input', 1),
        ('io_in_bits_uop_lqIdx_flag', 'input', 1),
        ('io_in_bits_uop_lqIdx_value', 'input', 7),
        ('io_in_bits_uop_sqIdx_flag', 'input', 1),
        ('io_in_bits_uop_sqIdx_value', 'input', 6),
        ('io_in_bits_vaddr', 'input', 50),
        ('io_in_bits_paddr', 'input', 48),
        ('io_in_bits_data', 'input', 129),
        ('io_in_bits_isvec', 'input', 1),
        ('io_in_bits_is128bit', 'input', 1),
        ('io_in_bits_vecActive', 'input', 1),
        ('io_in_bits_schedIndex', 'input', 7),
        ('io_out_ready', 'input', 1),
        ('io_out_valid', 'output', 1),
        ('io_out_bits_uop_exceptionVec_4', 'output', 1),
        ('io_out_bits_uop_exceptionVec_19', 'output', 1),
        ('io_out_bits_uop_preDecodeInfo_isRVC', 'output', 1),
        ('io_out_bits_uop_ftqPtr_flag', 'output', 1),
        ('io_out_bits_uop_ftqPtr_value', 'output', 6),
        ('io_out_bits_uop_ftqOffset', 'output', 4),
        ('io_out_bits_uop_fuOpType', 'output', 9),
        ('io_out_bits_uop_rfWen', 'output', 1),
        ('io_out_bits_uop_fpWen', 'output', 1),
        ('io_out_bits_uop_vpu_vstart', 'output', 8),
        ('io_out_bits_uop_vpu_veew', 'output', 2),
        ('io_out_bits_uop_uopIdx', 'output', 7),
        ('io_out_bits_uop_pdest', 'output', 8),
        ('io_out_bits_uop_robIdx_flag', 'output', 1),
        ('io_out_bits_uop_robIdx_value', 'output', 8),
        ('io_out_bits_uop_storeSetHit', 'output', 1),
        ('io_out_bits_uop_waitForRobIdx_flag', 'output', 1),
        ('io_out_bits_uop_waitForRobIdx_value', 'output', 8),
        ('io_out_bits_uop_loadWaitBit', 'output', 1),
        ('io_out_bits_uop_loadWaitStrict', 'output', 1),
        ('io_out_bits_uop_lqIdx_flag', 'output', 1),
        ('io_out_bits_uop_lqIdx_value', 'output', 7),
        ('io_out_bits_uop_sqIdx_flag', 'output', 1),
        ('io_out_bits_uop_sqIdx_value', 'output', 6),
        ('io_out_bits_vaddr', 'output', 50),
        ('io_out_bits_paddr', 'output', 48),
        ('io_out_bits_data', 'output', 129),
        ('io_out_bits_isvec', 'output', 1),
        ('io_out_bits_is128bit', 'output', 1),
        ('io_out_bits_vecActive', 'output', 1),
        ('io_out_bits_schedIndex', 'output', 7),
    ),
    'PipelineRegModule_6': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_in_ready', 'output', 1),
        ('io_in_valid', 'input', 1),
        ('io_in_bits_data', 'input', 64),
        ('io_in_bits_id', 'input', 4),
        ('io_in_bits_nc', 'input', 1),
        ('io_in_bits_is2lq', 'input', 1),
        ('io_in_bits_denied', 'input', 1),
        ('io_in_bits_corrupt', 'input', 1),
        ('io_out_ready', 'input', 1),
        ('io_out_valid', 'output', 1),
        ('io_out_bits_data', 'output', 64),
        ('io_out_bits_id', 'output', 4),
        ('io_out_bits_nc', 'output', 1),
        ('io_out_bits_is2lq', 'output', 1),
        ('io_out_bits_denied', 'output', 1),
        ('io_out_bits_corrupt', 'output', 1),
    ),
}

# =============================================================================
# Implementation
# =============================================================================
class PipelineRegFamily(Elaboratable):
    """One V2 single-entry ready/valid elastic register. / 一个 V2 单项 ready/valid 弹性寄存器。"""

    def __init__(self, member: str = "PipelineRegModule") -> None:
        """Declare one selected bundle specialization. / 声明选定的 bundle 特化。"""

        if member not in PORT_SPECS:
            raise ValueError(f"unsupported pipeline member: {member}")
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports: dict[str, Signal] = {
            name: Signal(width, name=name) for name, _direction, width in self.specs
        }
        self.clock = self.ports["clock"]
        self.reset = self.ports["reset"]

    # Elaborate the source Decoupled register state machine. / 展开源 Decoupled 寄存器状态机。
    def elaborate(self, platform: Any) -> Module:
        """Capture on input fire, clear on output fire, and expose backpressure. /
        在输入 fire 时捕获、输出 fire 时清空并产生反压。
        """

        del platform
        module = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        module.domains += domain
        valid = Signal(name="pipeline_reg_valid", reset=0)
        ready = ~valid | self.ports["io_out_ready"]
        in_fire = self.ports["io_in_valid"] & ready
        out_fire = valid & self.ports["io_out_ready"]
        module.d.comb += [
            self.ports["io_in_ready"].eq(ready),
            self.ports["io_out_valid"].eq(valid),
        ]
        fields = FIELD_LAYOUTS[self.member]
        registers: dict[str, Signal] = {}
        for name, width in fields:
            register = Signal(width, name=f"io_out_bits_r_{name}", reset_less=True)
            registers[name] = register
            module.d.comb += self.ports[f"io_out_bits_{name}"].eq(register)
            with cast(Any, module.If(in_fire)):
                module.d.sync += register.eq(self.ports[f"io_in_bits_{name}"])
        with cast(Any, module.If(in_fire)):
            module.d.sync += valid.eq(1)
        with cast(Any, module.Elif(out_fire)):
            module.d.sync += valid.eq(0)
        return module


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    """Export one deterministic same-name pipeline member. / 导出确定性的同名流水成员。"""

    del injected_dependencies
    member = "PipelineRegModule"
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = PipelineRegFamily(member)
    return verilog.convert(top, name=member, ports=[top.ports[n] for n, _d, _w in top.specs], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the default pipeline register Verilog. / 打印默认流水寄存器 Verilog。"""

    print(build_verilog({"module": "PipelineRegModule"}, {}))


if __name__ == "__main__":
    main()
