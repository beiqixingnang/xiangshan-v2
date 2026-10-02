"""Behavioral delay primitives with the locked V2 member interfaces.
采用锁定 V2 成员接口的行为延迟原语。
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping, cast

from amaranth import Cat, ClockDomain, ClockSignal, Const, Elaboratable, Module
from amaranth import ResetSignal, Signal, Value
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# One family Build implements unconditional delay, valid-gated delay,
# enable-gated resettable delay, and flushable ExuInput pipelines. Each public
# member is selected by its module name and emits that exact top name and port
# ABI. Configuration below contains only public field layout and geometry;
# all data fields are generated into real signals and equations.
# Resetless data registers have no reset branch. Their power-on relation to
# arbitrary external state requires a separate startup acceptance proof.
__all__ = [
    "DelayPort",
    "DelayField",
    "PipeFlushConfig",
    "DelayFamilyConfig",
    "DelayFamily",
    "MEMBER_NAMES",
    "COVERED_MODULES",
    "IMPLEMENTED_MEMBERS",
    "CONTRACT_ONLY_MEMBERS",
    "family_configuration",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
DelayMode = Literal["plain", "valid", "enabled", "pipe"]


@dataclass(frozen=True)
class DelayPort:
    """One named scalar or vector control port. / 一个命名标量或向量控制端口。"""

    name: str
    width: int = 1


@dataclass(frozen=True)
class DelayField:
    """Paired public payload ports and the corresponding state field. / 配对负载端口及对应状态字段。"""

    input_name: str
    output_name: str
    width: int
    state_name: str


@dataclass(frozen=True)
class PipeFlushConfig:
    """Public port roles used by the specialized flush equation. / 专用冲刷方程使用的公开端口角色。"""

    enq_rob_flag: str | None = None
    enq_rob_value: str | None = None
    redirect_valid: str | None = None
    redirect_rob_flag: str | None = None
    redirect_rob_value: str | None = None
    redirect_level: str | None = None
    load_dependencies: tuple[str, ...] = ()
    load_cancel_pairs: tuple[tuple[str | None, str | None], ...] = ()
    og0_fail: str | None = None
    og1_fail: str | None = None


@dataclass(frozen=True)
class DelayFamilyConfig:
    """Compact geometry and exact public layout for one family member. / 一个族成员的紧凑几何与精确公开布局。"""

    member_name: str
    mode: DelayMode
    stages: int
    data_fields: tuple[DelayField, ...]
    control_inputs: tuple[DelayPort, ...] = ()
    control_outputs: tuple[DelayPort, ...] = ()
    clock_name: str | None = "clock"
    reset_name: str | None = None
    valid_input_name: str | None = None
    valid_output_name: str | None = None
    enable_name: str | None = None
    valid_has_init: bool = False
    pipe_flush: PipeFlushConfig | None = None
    pipe_modify_fields: tuple[str, ...] = ()


def make_fields(mode: DelayMode, fields: tuple[tuple[str, int], ...]) -> tuple[DelayField, ...]:
    """Expand compact suffix/width declarations into exact data port names. / 将紧凑后缀/位宽声明展开为精确数据端口名。"""

    result = []
    for suffix, width in fields:
        if mode == "plain":
            input_name, output_name = (
                ("io_in", "io_out") if suffix == "" else
                (f"io_in_{suffix}", f"io_out_{suffix}")
            )
        elif mode == "valid":
            input_name, output_name = (
                ("io_in_bits", "io_out_bits") if suffix == "" else
                (f"io_in_bits_{suffix}", f"io_out_bits_{suffix}")
            )
        elif mode == "enabled":
            input_name, output_name = f"i_{suffix}", f"o_{suffix}"
        else:
            input_name, output_name = f"io_enq_bits_{suffix}", f"io_deq_bits_{suffix}"
        result.append(DelayField(input_name, output_name, width, suffix))
    return tuple(result)


def numbered_fields(prefix: str, count: int, width: int) -> tuple[tuple[str, int], ...]:
    """Generate a real repeated public vector layout. / 生成实际重复的公开向量布局。"""

    return tuple((f"{prefix}{index}", width) for index in range(count))


def control_ports(names: tuple[str, ...], widths: Mapping[str, int] | None = None) -> tuple[DelayPort, ...]:
    width_map = widths or {}
    return tuple(DelayPort(name, width_map.get(name, 1)) for name in names)


def plain_config(member_name: str, stages: int,
                 fields: tuple[tuple[str, int], ...]) -> DelayFamilyConfig:
    data = make_fields("plain", fields)
    return DelayFamilyConfig(member_name, "plain", stages, data,
                             control_inputs=control_ports(("clock",)) if stages else (),
                             clock_name="clock" if stages else None)


def valid_config(member_name: str, stages: int, fields: tuple[tuple[str, int], ...],
                 *, has_reset: bool, has_valid_input: bool,
                 has_valid_output: bool) -> DelayFamilyConfig:
    data = make_fields("valid", fields)
    controls = []
    if stages:
        controls.append(DelayPort("clock"))
    if has_reset:
        controls.append(DelayPort("reset"))
    if has_valid_input:
        controls.append(DelayPort("io_in_valid"))
    outputs = (DelayPort("io_out_valid"),) if has_valid_output else ()
    return DelayFamilyConfig(
        member_name, "valid", stages, data, tuple(controls), outputs,
        clock_name="clock" if stages else None,
        reset_name="reset" if has_reset else None,
        valid_input_name="io_in_valid" if has_valid_input else None,
        valid_output_name="io_out_valid" if has_valid_output else None,
        valid_has_init=has_reset,
    )


def enabled_config(member_name: str, stages: int,
                   fields: tuple[tuple[str, int], ...]) -> DelayFamilyConfig:
    return DelayFamilyConfig(
        member_name, "enabled", stages, make_fields("enabled", fields),
        control_inputs=control_ports(("clock", "reset")),
        clock_name="clock", reset_name="reset",
    )


def pipe_config(member_name: str, stages: int,
                fields: tuple[tuple[str, int], ...], *,
                flush_controls: tuple[str, ...] = (),
                load_cancel_pairs: tuple[tuple[str | None, str | None], ...] = ()) -> DelayFamilyConfig:
    data = make_fields("pipe", fields)
    controls = []
    if stages:
        controls.extend((DelayPort("clock"), DelayPort("reset")))
    controls.append(DelayPort("io_enq_valid"))
    controls.extend(control_ports(
        flush_controls,
        {name: 8 for name in flush_controls
         if name.endswith("redirect_bits_robIdx_value")},
    ))
    outputs = (DelayPort("io_deq_valid"),)
    field_names = {field.input_name for field in data}
    dependencies = tuple(field.input_name for field in data
                         if "loadDependency_" in field.input_name)
    has_rob = "io_enq_bits_robIdx_flag" in field_names and "io_enq_bits_robIdx_value" in field_names
    control_names = {port.name for port in controls}
    flush = PipeFlushConfig(
        enq_rob_flag="io_enq_bits_robIdx_flag" if has_rob else None,
        enq_rob_value="io_enq_bits_robIdx_value" if has_rob else None,
        redirect_valid="io_flush_redirect_valid" if "io_flush_redirect_valid" in control_names else None,
        redirect_rob_flag="io_flush_redirect_bits_robIdx_flag" if "io_flush_redirect_bits_robIdx_flag" in control_names else None,
        redirect_rob_value="io_flush_redirect_bits_robIdx_value" if "io_flush_redirect_bits_robIdx_value" in control_names else None,
        redirect_level="io_flush_redirect_bits_level" if "io_flush_redirect_bits_level" in control_names else None,
        load_dependencies=dependencies,
        load_cancel_pairs=load_cancel_pairs,
        og0_fail="io_flush_og0Fail" if "io_flush_og0Fail" in control_names else None,
        og1_fail="io_flush_og1Fail" if "io_flush_og1Fail" in control_names else None,
    )
    return DelayFamilyConfig(
        member_name, "pipe", stages, data, tuple(controls), outputs,
        clock_name="clock" if stages else None,
        reset_name="reset" if stages else None,
        valid_input_name="io_enq_valid",
        valid_output_name="io_deq_valid",
        pipe_flush=flush,
        pipe_modify_fields=dependencies,
    )


def create_family_configurations() -> Mapping[str, DelayFamilyConfig]:
    """Build the finite, product-owned interface/geometry configuration. / 构造有限且由产品维护的接口/几何配置。"""

    configurations: dict[str, DelayFamilyConfig] = {}
    add = configurations.__setitem__

    add("DelayN", plain_config("DelayN", 1, (
        ("ubtb_enable", 1), ("btb_enable", 1), ("tage_enable", 1),
        ("sc_enable", 1), ("ras_enable", 1),
    )))
    for name, stages, width in (
        ("DelayN_1", 2, 1), ("DelayN_13", 1, 1), ("DelayN_15", 4, 1),
        ("DelayN_17", 5, 1), ("DelayN_208", 5, 8), ("DelayN_225", 0, 1),
        ("DelayN_297", 3, 1), ("DelayN_331", 10, 1), ("DelayN_334", 5, 48),
    ):
        add(name, plain_config(name, stages, (("", width),)))

    add("DelayN_7", plain_config("DelayN_7", 2, (
        ("satp_mode", 4), ("satp_asid", 16), ("satp_changed", 1),
        ("vsatp_mode", 4), ("vsatp_asid", 16), ("vsatp_changed", 1),
        ("hgatp_mode", 4), ("hgatp_vmid", 16), ("hgatp_changed", 1),
        ("mbmc_BME", 1), ("mbmc_CMODE", 1), ("priv_mxr", 1),
        ("priv_sum", 1), ("priv_vmxr", 1), ("priv_vsum", 1),
        ("priv_virt", 1), ("priv_virt_changed", 1), ("priv_spvp", 1),
        ("priv_imode", 2), ("priv_dmode", 2), ("priv_debug", 1),
        ("pmm_mseccfg", 2), ("pmm_menvcfg", 2), ("pmm_henvcfg", 2),
        ("pmm_hstatus", 2), ("pmm_senvcfg", 2),
    )))
    add("DelayN_8", plain_config("DelayN_8", 2, (
        ("pf_ctrl_l1I_pf_enable", 1), ("bp_ctrl_ubtb_enable", 1),
        ("bp_ctrl_btb_enable", 1), ("bp_ctrl_tage_enable", 1),
        ("bp_ctrl_sc_enable", 1), ("bp_ctrl_ras_enable", 1),
        ("sbuffer_timeout", 22), ("ldld_vio_check_enable", 1),
        ("cache_error_enable", 1), ("hd_misalign_st_enable", 1),
        ("hd_misalign_ld_enable", 1), ("distribute_csr_w_valid", 1),
        ("distribute_csr_w_bits_addr", 12), ("distribute_csr_w_bits_data", 64),
        ("frontend_trigger_tUpdate_valid", 1), ("frontend_trigger_tUpdate_bits_addr", 2),
        ("frontend_trigger_tUpdate_bits_tdata_matchType", 2),
        ("frontend_trigger_tUpdate_bits_tdata_select", 1),
        ("frontend_trigger_tUpdate_bits_tdata_action", 4),
        ("frontend_trigger_tUpdate_bits_tdata_chain", 1),
        ("frontend_trigger_tUpdate_bits_tdata_tdata2", 64),
        ("frontend_trigger_tEnableVec_0", 1), ("frontend_trigger_tEnableVec_1", 1),
        ("frontend_trigger_tEnableVec_2", 1), ("frontend_trigger_tEnableVec_3", 1),
        ("frontend_trigger_debugMode", 1), ("frontend_trigger_triggerCanRaiseBpExp", 1),
        ("mem_trigger_tUpdate_valid", 1), ("mem_trigger_tUpdate_bits_addr", 2),
        ("mem_trigger_tUpdate_bits_tdata_matchType", 2),
        ("mem_trigger_tUpdate_bits_tdata_select", 1),
        ("mem_trigger_tUpdate_bits_tdata_action", 4),
        ("mem_trigger_tUpdate_bits_tdata_chain", 1),
        ("mem_trigger_tUpdate_bits_tdata_store", 1),
        ("mem_trigger_tUpdate_bits_tdata_load", 1),
        ("mem_trigger_tUpdate_bits_tdata_tdata2", 64),
        ("mem_trigger_tEnableVec_0", 1), ("mem_trigger_tEnableVec_1", 1),
        ("mem_trigger_tEnableVec_2", 1), ("mem_trigger_tEnableVec_3", 1),
        ("mem_trigger_debugMode", 1), ("mem_trigger_triggerCanRaiseBpExp", 1),
        ("fsIsOff", 1),
    )))
    add("DelayN_9", plain_config("DelayN_9", 2, (
        ("valid", 1), ("bits_rs1", 1), ("bits_rs2", 1), ("bits_addr", 50),
        ("bits_id", 16), ("bits_flushPipe", 1), ("bits_hv", 1), ("bits_hg", 1),
    )))
    add("DelayN_214", plain_config("DelayN_214", 2, (
        ("valid", 1), ("bits_pc", 50),
        *numbered_fields("bits_exceptionVec_", 24, 1),
        ("bits_isPcBkpt", 1), ("bits_isFetchMalAddr", 1),
        ("bits_satpFlushFirstFetchFault", 1), ("bits_gpaddr", 64),
        ("bits_singleStep", 1), ("bits_crossPageIPFFix", 1),
        ("bits_isInterrupt", 1), ("bits_isHls", 1), ("bits_trigger", 4),
        ("bits_isForVSnonLeafPTE", 1),
    )))
    add("DelayN_215", plain_config("DelayN_215", 2, (("flag", 1), ("value", 8))))
    add("DelayN_220", plain_config("DelayN_220", 1, (
        ("valid", 1), ("bits_rs1", 1), ("bits_rs2", 1), ("bits_addr", 50),
        ("bits_id", 16), ("bits_hv", 1), ("bits_hg", 1),
    )))
    add("DelayN_221", plain_config("DelayN_221", 1, (
        ("satp_mode", 4), ("satp_asid", 16), ("satp_ppn", 44),
        ("satp_changed", 1), ("vsatp_mode", 4), ("vsatp_asid", 16),
        ("vsatp_ppn", 44), ("vsatp_changed", 1), ("hgatp_mode", 4),
        ("hgatp_vmid", 16), ("hgatp_ppn", 44), ("hgatp_changed", 1),
        ("mbmc_BME", 1), ("mbmc_CMODE", 1), ("mbmc_BCLEAR", 1),
        ("mbmc_BMA", 58), ("priv_virt", 1), ("priv_virt_changed", 1),
        ("priv_debug", 1), ("mPBMTE", 1), ("hPBMTE", 1),
    )))
    add("DelayN_333", plain_config("DelayN_333", 2, (
        ("l2_pf_master_en", 1), ("l2_pf_recv_en", 1), ("l2_pbop_en", 1),
        ("l2_vbop_en", 1), ("l2_tp_en", 1), ("l2_pf_delay_latency", 10),
    )))

    add("DelayNWithValid", valid_config("DelayNWithValid", 2, (("", 50),),
        has_reset=True, has_valid_input=True, has_valid_output=False))
    add("DelayNWithValid_1", valid_config("DelayNWithValid_1", 2, (
        ("isCall", 1), ("isRet", 1), ("isJalr", 1), ("valid", 1),
        ("brSlots_0_offset", 4), ("brSlots_0_sharing", 1),
        ("brSlots_0_valid", 1), ("brSlots_0_lower", 12),
        ("brSlots_0_tarStat", 2), ("tailSlot_offset", 4),
        ("tailSlot_sharing", 1), ("tailSlot_valid", 1),
        ("tailSlot_lower", 20), ("tailSlot_tarStat", 2),
        ("pftAddr", 4), ("carry", 1), ("last_may_be_rvi_call", 1),
        ("strong_bias_0", 1), ("strong_bias_1", 1),
    ), has_reset=True, has_valid_input=True, has_valid_output=False))
    for name, stages, fields, has_reset, has_valid_input, has_valid_output in (
        ("DelayNWithValid_2", 2, (("paddr", 48), ("report_to_beu", 1)), True, True, True),
        ("DelayNWithValid_3", 2, (("", 48),), True, True, True),
        ("DelayNWithValid_4", 0, (("", 9),), False, False, False),
        ("DelayNWithValid_7", 0, (("", 16),), False, False, False),
        ("DelayNWithValid_52", 1, (("", 4),), False, True, False),
        ("DelayNWithValid_55", 1, (("", 24),), False, True, False),
        ("DelayNWithValid_103", 1, (("", 16),), False, True, False),
        ("DelayNWithValid_152", 1, (("", 9),), False, True, False),
        ("DelayNWithValid_155", 1, (("", 50),), False, True, False),
        ("DelayNWithValid_200", 2, (("addr", 48), ("source", 5)), True, True, True),
        ("DelayNWithValid_202", 1, (("", 12),), True, True, True),
        ("DelayNWithValid_203", 1, (("", 64),), True, True, True),
    ):
        add(name, valid_config(name, stages, fields, has_reset=has_reset,
                               has_valid_input=has_valid_input,
                               has_valid_output=has_valid_output))

    delay_reg_fields = (
        ("valid", 1), ("skip", 1), ("isRVC", 1), ("rfwen", 1),
        ("fpwen", 1), ("vecwen", 1), ("v0wen", 1), ("wpdest", 9),
        ("wdest", 8), *numbered_fields("otherwpdest_", 16, 9),
        ("pc", 64), ("instr", 32), ("robIdx", 10), ("lqIdx", 7),
        ("sqIdx", 7), ("isLoad", 1), ("isStore", 1), ("nFused", 8),
        ("special", 8), ("coreid", 8), ("index", 8),
    )
    add("DelayReg", enabled_config("DelayReg", 3, delay_reg_fields))
    add("DelayReg_8", enabled_config("DelayReg_8", 2,
        (*numbered_fields("value_", 32, 8), ("coreid", 8))))
    add("DelayReg_10", enabled_config("DelayReg_10", 2,
        (*numbered_fields("value_", 64, 9), ("coreid", 8))))
    add("DelayReg_11", enabled_config("DelayReg_11", 2,
        (*numbered_fields("value_", 224, 64), ("coreid", 8))))
    add("DelayReg_12", enabled_config("DelayReg_12", 2,
        (*numbered_fields("value_", 192, 64), ("coreid", 8))))
    add("DelayReg_13", enabled_config("DelayReg_13", 2,
        (*numbered_fields("value_", 300, 64), ("coreid", 8))))
    add("DelayReg_14", enabled_config("DelayReg_14", 3, (
        ("valid", 1), ("interrupt", 32), ("exception", 32),
        ("exceptionPC", 64), ("exceptionInst", 32), ("hasNMI", 1),
        ("virtualInterruptIsHvictlInject", 1), ("irToHS", 1),
        ("irToVS", 1), ("coreid", 8),
    )))
    add("DelayReg_15", enabled_config("DelayReg_15", 4, (
        ("valid", 1), ("criticalError", 1), ("coreid", 8),
    )))

    add("PipeWithFlush", pipe_config("PipeWithFlush", 0, (
        ("fuType", 35), ("pdest", 8), ("rfWen", 1),
        ("loadDependency_0", 2), ("loadDependency_1", 2),
        ("loadDependency_2", 2),
    )))
    add("PipeWithFlush_1", pipe_config("PipeWithFlush_1", 2, (
        ("fuType", 35), ("robIdx_flag", 1), ("robIdx_value", 8),
        ("pdest", 8), ("rfWen", 1), ("loadDependency_0", 2),
        ("loadDependency_1", 2), ("loadDependency_2", 2),
    ), flush_controls=(
        "io_flush_redirect_valid", "io_flush_redirect_bits_robIdx_flag",
        "io_flush_redirect_bits_robIdx_value", "io_flush_redirect_bits_level",
        "io_flush_ldCancel_0_ld2Cancel", "io_flush_ldCancel_1_ld2Cancel",
        "io_flush_ldCancel_2_ld2Cancel", "io_flush_og0Fail",
    ), load_cancel_pairs=((None, "io_flush_ldCancel_0_ld2Cancel"),
                          (None, "io_flush_ldCancel_1_ld2Cancel"),
                          (None, "io_flush_ldCancel_2_ld2Cancel"))))
    for name, stages, fields, flush_controls in (
        ("PipeWithFlush_6", 1, (
            ("fuType", 35), ("robIdx_flag", 1), ("robIdx_value", 8),
            ("pdest", 8), ("fpWen", 1), ("vecWen", 1), ("v0Wen", 1),
        ), ()),
        ("PipeWithFlush_7", 2, (
            ("fuType", 35), ("robIdx_flag", 1), ("robIdx_value", 8),
            ("pdest", 8), ("fpWen", 1), ("vecWen", 1), ("v0Wen", 1),
        ), ("io_flush_redirect_valid", "io_flush_redirect_bits_robIdx_flag",
            "io_flush_redirect_bits_robIdx_value", "io_flush_redirect_bits_level",
            "io_flush_og0Fail")),
        ("PipeWithFlush_8", 0, (
            ("fuType", 35), ("pdest", 8), ("fpWen", 1),
            ("vecWen", 1), ("v0Wen", 1),
        ), ()),
        ("PipeWithFlush_9", 3, (
            ("fuType", 35), ("robIdx_flag", 1), ("robIdx_value", 8),
            ("pdest", 8), ("fpWen", 1), ("vecWen", 1), ("v0Wen", 1),
        ), ("io_flush_redirect_valid", "io_flush_redirect_bits_robIdx_flag",
            "io_flush_redirect_bits_robIdx_value", "io_flush_redirect_bits_level",
            "io_flush_og0Fail")),
        ("PipeWithFlush_10", 1, (
            ("robIdx_flag", 1), ("robIdx_value", 8), ("pdest", 8), ("fpWen", 1),
        ), ()),
        ("PipeWithFlush_11", 3, (
            ("robIdx_flag", 1), ("robIdx_value", 8), ("pdest", 8), ("fpWen", 1),
        ), ("io_flush_redirect_valid", "io_flush_redirect_bits_robIdx_flag",
            "io_flush_redirect_bits_robIdx_value", "io_flush_redirect_bits_level",
            "io_flush_og0Fail")),
    ):
        add(name, pipe_config(name, stages, fields, flush_controls=flush_controls))

    return MappingProxyType(configurations)


FAMILY_CONFIGURATIONS = create_family_configurations()
MEMBER_NAMES = (
    "DelayN", "DelayN_1", "DelayN_13", "DelayN_15", "DelayN_17",
    "DelayN_208", "DelayN_214", "DelayN_215", "DelayN_220", "DelayN_221",
    "DelayN_225", "DelayN_297", "DelayN_331", "DelayN_333", "DelayN_334",
    "DelayN_7", "DelayN_8", "DelayN_9",
    "DelayNWithValid", "DelayNWithValid_1", "DelayNWithValid_103",
    "DelayNWithValid_152", "DelayNWithValid_155", "DelayNWithValid_2",
    "DelayNWithValid_200", "DelayNWithValid_202", "DelayNWithValid_203",
    "DelayNWithValid_3", "DelayNWithValid_4", "DelayNWithValid_52",
    "DelayNWithValid_55", "DelayNWithValid_7",
    "DelayReg", "DelayReg_8", "DelayReg_10", "DelayReg_11",
    "DelayReg_12", "DelayReg_13", "DelayReg_14", "DelayReg_15",
    "PipeWithFlush", "PipeWithFlush_1", "PipeWithFlush_6", "PipeWithFlush_7",
    "PipeWithFlush_8", "PipeWithFlush_9", "PipeWithFlush_10", "PipeWithFlush_11",
)
COVERED_MODULES = (
    "DelayN", "DelayN_1", "DelayN_13", "DelayN_15", "DelayN_17",
    "DelayN_208", "DelayN_214", "DelayN_215", "DelayN_220", "DelayN_221",
    "DelayN_225", "DelayN_297", "DelayN_331", "DelayN_333", "DelayN_334",
    "DelayN_7", "DelayN_8", "DelayN_9",
    "DelayNWithValid", "DelayNWithValid_1", "DelayNWithValid_103",
    "DelayNWithValid_152", "DelayNWithValid_155", "DelayNWithValid_2",
    "DelayNWithValid_200", "DelayNWithValid_202", "DelayNWithValid_203",
    "DelayNWithValid_3", "DelayNWithValid_4", "DelayNWithValid_52",
    "DelayNWithValid_55", "DelayNWithValid_7",
    "DelayReg", "DelayReg_8", "DelayReg_10", "DelayReg_11",
    "DelayReg_12", "DelayReg_13", "DelayReg_14", "DelayReg_15",
    "PipeWithFlush", "PipeWithFlush_1", "PipeWithFlush_6", "PipeWithFlush_7",
    "PipeWithFlush_8", "PipeWithFlush_9", "PipeWithFlush_10", "PipeWithFlush_11",
)
IMPLEMENTED_MEMBERS = COVERED_MODULES
CONTRACT_ONLY_MEMBERS: tuple[str, ...] = ()
if set(COVERED_MODULES) != set(FAMILY_CONFIGURATIONS):
    raise RuntimeError("covered member names and product configurations must match")


# =============================================================================
# Implementation
# =============================================================================
class DelayFamily(Elaboratable):
    """Elaborate one exactly configured delay member. / 展开一个精确配置的延迟成员。"""

    def __init__(self, configuration: DelayFamilyConfig) -> None:
        self.configuration = configuration
        self.inputs = {
            port.name: Signal(port.width, name=port.name)
            for port in configuration.control_inputs
        }
        self.outputs = {
            port.name: Signal(port.width, name=port.name)
            for port in configuration.control_outputs
        }
        for field in configuration.data_fields:
            self.inputs[field.input_name] = Signal(field.width, name=field.input_name)
            self.outputs[field.output_name] = Signal(field.width, name=field.output_name)
        self.ports = tuple(self.inputs.values()) + tuple(self.outputs.values())

    @staticmethod
    def state_reset_applies(configuration: DelayFamilyConfig,
                            *, valid_state: bool = False) -> bool:
        if configuration.reset_name is None:
            return False
        if configuration.mode == "enabled":
            return True
        if configuration.mode == "pipe":
            return valid_state
        return configuration.mode == "valid" and valid_state and configuration.valid_has_init

    @staticmethod
    def state_name(configuration: DelayFamilyConfig,
                   field: DelayField, stage: int) -> str:
        suffix = field.state_name
        if configuration.mode == "plain":
            return ("REG" if stage == 0 else f"REG_{stage}") if not suffix else (
                f"REG_{suffix}" if stage == 0 else f"REG_{stage}_{suffix}"
            )
        if configuration.mode == "valid":
            if configuration.stages == 1:
                return "res_bits" if not suffix else f"res_bits_{suffix}"
            return (("data" if stage == 0 else "res_bits") if not suffix else
                    (f"data_{suffix}" if stage == 0 else f"res_bits_{suffix}"))
        if configuration.mode == "enabled":
            return f"r_{stage + 1}_{suffix}" if suffix else f"r_{stage + 1}"
        return f"bits_{stage + 1}_{suffix}" if suffix else f"bits_{stage + 1}"

    def pipe_flush(self, stage: int, stage_data: dict[str, Value]) -> Value:
        role = self.configuration.pipe_flush
        if role is None:
            return Const(0)
        terms: list[Value] = []
        if (role.enq_rob_flag is not None and role.enq_rob_value is not None
                and role.redirect_valid is not None and role.redirect_rob_flag is not None
                and role.redirect_rob_value is not None and role.redirect_level is not None):
            pointer_flag = stage_data[role.enq_rob_flag]
            pointer_value = stage_data[role.enq_rob_value]
            redirect_flag = self.inputs[role.redirect_rob_flag]
            redirect_value = self.inputs[role.redirect_rob_value]
            equal = (pointer_flag == redirect_flag) & (pointer_value == redirect_value)
            after = (pointer_flag ^ redirect_flag) ^ (pointer_value > redirect_value)
            terms.append(self.inputs[role.redirect_valid] & (
                (self.inputs[role.redirect_level] & equal) | after
            ))
        for dependency_name, pair in zip(role.load_dependencies,
                                          role.load_cancel_pairs, strict=False):
            dependency = stage_data[dependency_name]
            ld1_name, ld2_name = pair
            if ld1_name is not None:
                terms.append(self.inputs[ld1_name] & dependency[0])
            if ld2_name is not None:
                terms.append(self.inputs[ld2_name] & dependency[1])
        if stage == 1 and role.og0_fail is not None:
            terms.append(self.inputs[role.og0_fail])
        if stage == 2 and role.og1_fail is not None:
            terms.append(self.inputs[role.og1_fail])
        if not terms:
            return Const(0)
        result: Value = terms[0]
        for term in terms[1:]:
            result = result | term
        return result

    def modify_pipe_field(self, field: DelayField, value: Value) -> Value:
        if field.input_name in self.configuration.pipe_modify_fields:
            return value << 1
        return value

    def elaborate(self, platform: object) -> Module:
        del platform
        module = Module()
        cfg = self.configuration
        if cfg.stages == 0:
            for field in cfg.data_fields:
                module.d.comb += self.outputs[field.output_name].eq(self.inputs[field.input_name])
            if cfg.valid_output_name is not None and cfg.valid_input_name is not None:
                module.d.comb += self.outputs[cfg.valid_output_name].eq(self.inputs[cfg.valid_input_name])
            return module

        async_reset = (self.state_reset_applies(cfg)
                       or self.state_reset_applies(cfg, valid_state=True))
        if cfg.clock_name is None:
            raise ValueError("a registered delay requires its clock input")
        if async_reset:
            if cfg.reset_name is None:
                raise ValueError("a resettable delay requires its reset input")
            module.domains += ClockDomain("delay", async_reset=True, local=True)
            module.d.comb += [
                ClockSignal("delay").eq(self.inputs[cfg.clock_name]),
                ResetSignal("delay").eq(self.inputs[cfg.reset_name]),
            ]
        else:
            module.domains += ClockDomain("delay", reset_less=True, local=True)
            module.d.comb += ClockSignal("delay").eq(self.inputs[cfg.clock_name])

        state: list[dict[str, Signal]] = []
        for stage in range(cfg.stages):
            row: dict[str, Signal] = {}
            reset_stage = self.state_reset_applies(cfg)
            for field in cfg.data_fields:
                state_name = self.state_name(cfg, field, stage)
                discarded_bits = min(stage, field.width) if (
                    cfg.mode == "pipe" and field.input_name in cfg.pipe_modify_fields) else 0
                row[field.input_name] = Signal(
                    field.width - discarded_bits,
                    name=state_name,
                    reset=0,
                    reset_less=not reset_stage,
                )
            state.append(row)

        def state_value(stage: int, field: DelayField) -> Value:
            stored = state[stage][field.input_name]
            discarded_bits = min(stage, field.width) if (
                cfg.mode == "pipe" and field.input_name in cfg.pipe_modify_fields) else 0
            return cast(Value, Cat(Const(0, discarded_bits), stored)) if discarded_bits else stored

        valid_state: list[Signal] = []
        if cfg.mode in ("valid", "pipe"):
            for stage in range(cfg.stages):
                if cfg.mode == "pipe":
                    name = f"valids_{stage + 1}"
                else:
                    name = "valid_REG" if stage == 0 else f"valid_REG_{stage}"
                reset_valid = self.state_reset_applies(cfg, valid_state=True)
                valid_signal = Signal(name=name, reset=0, reset_less=not reset_valid)
                valid_state.append(valid_signal)

        if cfg.mode == "plain":
            for stage in range(cfg.stages):
                for field in cfg.data_fields:
                    source = (self.inputs[field.input_name] if stage == 0
                              else state[stage - 1][field.input_name])
                    module.d.delay += state[stage][field.input_name].eq(source)
        elif cfg.mode == "valid":
            if cfg.valid_input_name is None:
                raise ValueError("a valid-gated delay requires its valid input")
            for stage in range(cfg.stages):
                previous_valid = (self.inputs[cfg.valid_input_name] if stage == 0
                                  else valid_state[stage - 1])
                module.d.delay += valid_state[stage].eq(previous_valid)
                with cast(AbstractContextManager[None], module.If(previous_valid)):
                    for field in cfg.data_fields:
                        source = (self.inputs[field.input_name] if stage == 0
                                  else state[stage - 1][field.input_name])
                        module.d.delay += state[stage][field.input_name].eq(source)
        elif cfg.mode == "enabled":
            for stage in range(cfg.stages):
                if cfg.enable_name is None:
                    for field in cfg.data_fields:
                        source = (self.inputs[field.input_name] if stage == 0
                                  else state[stage - 1][field.input_name])
                        module.d.delay += state[stage][field.input_name].eq(source)
                else:
                    with cast(AbstractContextManager[None], module.If(self.inputs[cfg.enable_name])):
                        for field in cfg.data_fields:
                            source = (self.inputs[field.input_name] if stage == 0
                                      else state[stage - 1][field.input_name])
                            module.d.delay += state[stage][field.input_name].eq(source)
        else:
            if cfg.valid_input_name is None:
                raise ValueError("a flushable delay requires its valid input")
            for stage in range(cfg.stages):
                previous_valid = (self.inputs[cfg.valid_input_name] if stage == 0
                                  else valid_state[stage - 1])
                previous_data: dict[str, Value] = ({field.input_name: self.inputs[field.input_name]
                                  for field in cfg.data_fields} if stage == 0
                                 else {field.input_name: state_value(stage - 1, field)
                                       for field in cfg.data_fields})
                next_valid = previous_valid if stage == 0 else (
                    previous_valid & ~self.pipe_flush(stage, previous_data)
                )
                module.d.delay += valid_state[stage].eq(next_valid)
                with cast(AbstractContextManager[None], module.If(previous_valid)):
                    for field in cfg.data_fields:
                        source = previous_data[field.input_name]
                        if stage:
                            source = self.modify_pipe_field(field, source)
                        if field.input_name in cfg.pipe_modify_fields:
                            source = cast(Value, source[min(stage, field.width):])
                        module.d.delay += state[stage][field.input_name].eq(source)

        for field in cfg.data_fields:
            module.d.comb += self.outputs[field.output_name].eq(state_value(cfg.stages - 1, field))
        if cfg.valid_output_name is not None and valid_state:
            module.d.comb += self.outputs[cfg.valid_output_name].eq(valid_state[-1])
        return module


# =============================================================================
# Public Adapter
# =============================================================================
def family_configuration(module_name: str) -> DelayFamilyConfig:
    try:
        return FAMILY_CONFIGURATIONS[module_name]
    except KeyError as exc:
        raise ValueError(f"unknown delay member: {module_name}") from exc


def resolve_configuration(configuration: DelayFamilyConfig | dict[str, object] | str | None) -> DelayFamilyConfig:
    if configuration is None:
        return family_configuration("DelayN")
    if isinstance(configuration, str):
        return family_configuration(configuration)
    if isinstance(configuration, DelayFamilyConfig):
        if configuration.member_name not in FAMILY_CONFIGURATIONS:
            raise ValueError(f"configuration must select a declared family member: {configuration.member_name}")
        return configuration
    if isinstance(configuration, dict):
        module_name = configuration.get("module", "DelayN")
        if not isinstance(module_name, str):
            raise TypeError("configuration['module'] must be a string")
        return family_configuration(module_name)
    raise TypeError("configuration must be a member name, DelayFamilyConfig, dict, or None")


def build_verilog(configuration: DelayFamilyConfig | dict[str, object] | str | None = None,
                  injected_dependencies: dict[str, object] | None = None) -> str:
    del injected_dependencies
    cfg = resolve_configuration(configuration)
    top = DelayFamily(cfg)
    return verilog.convert(top, name=cfg.member_name, ports=top.ports,
                           emit_src=False, strip_internal_attrs=True)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
