"""Bounded Frontend BPU parent wiring for Kunminghu V2.
昆明湖 V2 前端 BPU 有界父级连线实现。

This aggregate keeps the already rewritten BPU leaves behind explicit
injection points and wires their clock, reset, request, update, and
prediction paths in one executable boundary.  It is a child-wiring closure,
not a claim that the complete FTB/TAGE/SC/FTQ hierarchy is finished.
该聚合将已重写的 BPU 叶子保留为显式注入点，在一个可执行边界内连接时钟、复位、
请求、更新和预测路径；它是子级连线闭包，不宣称完整 FTB/TAGE/SC/FTQ 层级已完成。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Elaboratable, Module, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# BpuParent wires the canonical FauFTBWay and FallThroughPredictor contracts,
# while exposing bounded observation ports for FTBEntryGen and state leaves.
# BpuParent 连接 FauFTBWay 与 FallThroughPredictor 标准契约，同时为 FTBEntryGen
# 及状态叶子暴露有界观测端口。
__all__ = ["BpuParentConfig", "BpuParent", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class BpuParentConfig:
    """Fixed V2 BPU field geometry. / 固定的 V2 BPU 字段几何。"""

    vaddr_bits: int = 50
    paddr_bits: int = 48
    tag_width: int = 16
    branch_offset_width: int = 4
    branch_lower_width: int = 12
    target_offset_width: int = 20
    target_status_width: int = 2
    prefetch_address_width: int = 4

    # Validate the locked Kunminghu V2 widths. / 校验锁定昆明湖 V2 位宽。
    def __post_init__(self) -> None:
        if self.vaddr_bits < self.paddr_bits:
            raise ValueError("V2 virtual address width must cover physical width")
        if min(self.tag_width, self.branch_offset_width, self.branch_lower_width,
               self.target_offset_width, self.target_status_width,
               self.prefetch_address_width) < 1:
            raise ValueError("BPU widths must be positive")


# =============================================================================
# Implementation
# =============================================================================
class BpuNullChild(Elaboratable):
    """Empty fallback for standalone envelope generation. / 独立包络生成用空回退子级。"""

    # Keep a real elaboratable object when no child was injected. / 未注入子级时仍提供可展开对象。
    def elaborate(self, platform: Any) -> Module:
        """Return an empty module. / 返回空模块。"""
        del platform
        return Module()


class BpuParent(Elaboratable):
    """Executable BPU child-wiring boundary. / 可执行的 BPU 子级连线边界。"""

    # Construct parent and child-visible ports. / 构造父级及子级可见端口。
    def __init__(self, configuration: BpuParentConfig | None = None,
                 injected_dependencies: dict[str, Any] | None = None) -> None:
        self.configuration = configuration or BpuParentConfig()
        cfg = self.configuration
        deps = injected_dependencies if isinstance(injected_dependencies, dict) else {}

        # Parent clock and prediction controls. / 父级时钟及预测控制。
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.enable = Signal(5, name="io_enable")
        self.reset_vector = Signal(cfg.paddr_bits, name="io_reset_vector")
        self.pc = Signal(cfg.vaddr_bits, name="io_pc")

        # FauFTBWay request/update and entry payload. / FauFTBWay 请求、更新及条目字段。
        self.req_tag = Signal(cfg.tag_width, name="io_req_tag")
        self.update_req_tag = Signal(cfg.tag_width, name="io_update_req_tag")
        self.write_valid = Signal(name="io_write_valid")
        self.write_tag = Signal(cfg.tag_width, name="io_write_tag")
        self.write_entry_is_call = Signal(name="io_write_entry_isCall")
        self.write_entry_is_ret = Signal(name="io_write_entry_isRet")
        self.write_entry_is_jalr = Signal(name="io_write_entry_isJalr")
        self.write_entry_valid = Signal(name="io_write_entry_valid")
        self.write_br_offset = Signal(cfg.branch_offset_width, name="io_write_entry_brSlots_0_offset")
        self.write_br_sharing = Signal(name="io_write_entry_brSlots_0_sharing")
        self.write_br_valid = Signal(name="io_write_entry_brSlots_0_valid")
        self.write_br_lower = Signal(cfg.branch_lower_width, name="io_write_entry_brSlots_0_lower")
        self.write_br_tar_stat = Signal(cfg.target_status_width, name="io_write_entry_brSlots_0_tarStat")
        self.write_tail_offset = Signal(cfg.branch_offset_width, name="io_write_entry_tailSlot_offset")
        self.write_tail_sharing = Signal(name="io_write_entry_tailSlot_sharing")
        self.write_tail_valid = Signal(name="io_write_entry_tailSlot_valid")
        self.write_tail_lower = Signal(cfg.target_offset_width, name="io_write_entry_tailSlot_lower")
        self.write_tail_tar_stat = Signal(cfg.target_status_width, name="io_write_entry_tailSlot_tarStat")
        self.write_pft_addr = Signal(cfg.prefetch_address_width, name="io_write_entry_pftAddr")
        self.write_carry = Signal(name="io_write_entry_carry")
        self.write_last_rvi_call = Signal(name="io_write_entry_last_may_be_rvi_call")
        self.write_strong_bias_0 = Signal(name="io_write_entry_strong_bias_0")
        self.write_strong_bias_1 = Signal(name="io_write_entry_strong_bias_1")

        # Fall-through stage inputs. / 顺序落空阶段输入。
        self.s0_fire = Signal(name="io_s0_fire")
        self.s1_fire = Signal(name="io_s1_fire")
        self.start_pc = Signal(cfg.vaddr_bits, name="io_start_pc")
        self.carry = Signal(name="io_carry")
        self.pft_addr = Signal(cfg.prefetch_address_width, name="io_pft_addr")
        self.entry_valid = Signal(name="io_entry_valid")
        self.entry_hit = Signal(name="io_entry_hit")

        # Child observations exported through the aggregate. / 通过聚合器导出的子级观测。
        self.resp_is_call = Signal(name="io_resp_isCall")
        self.resp_is_ret = Signal(name="io_resp_isRet")
        self.resp_is_jalr = Signal(name="io_resp_isJalr")
        self.resp_valid = Signal(name="io_resp_valid")
        self.resp_br_offset = Signal(cfg.branch_offset_width, name="io_resp_brSlots_0_offset")
        self.resp_br_sharing = Signal(name="io_resp_brSlots_0_sharing")
        self.resp_br_valid = Signal(name="io_resp_brSlots_0_valid")
        self.resp_br_lower = Signal(cfg.branch_lower_width, name="io_resp_brSlots_0_lower")
        self.resp_br_tar_stat = Signal(cfg.target_status_width, name="io_resp_brSlots_0_tarStat")
        self.resp_tail_offset = Signal(cfg.branch_offset_width, name="io_resp_tailSlot_offset")
        self.resp_tail_sharing = Signal(name="io_resp_tailSlot_sharing")
        self.resp_tail_valid = Signal(name="io_resp_tailSlot_valid")
        self.resp_tail_lower = Signal(cfg.target_offset_width, name="io_resp_tailSlot_lower")
        self.resp_tail_tar_stat = Signal(cfg.target_status_width, name="io_resp_tailSlot_tarStat")
        self.resp_pft_addr = Signal(cfg.prefetch_address_width, name="io_resp_pftAddr")
        self.resp_carry = Signal(name="io_resp_carry")
        self.resp_last_rvi_call = Signal(name="io_resp_last_may_be_rvi_call")
        self.resp_strong_bias_0 = Signal(name="io_resp_strong_bias_0")
        self.resp_strong_bias_1 = Signal(name="io_resp_strong_bias_1")
        self.resp_hit = Signal(name="io_resp_hit")
        self.update_hit = Signal(name="io_update_hit")
        self.pred_taken = Signal(name="io_pred_taken")
        self.pred_target = Signal(cfg.vaddr_bits, name="io_pred_target")
        self.pred_cfi_position = Signal(4, name="io_pred_cfi_position")
        self.fall_through_addr = Signal(cfg.vaddr_bits, name="io_fall_through_addr")
        self.fall_through_err = Signal(name="io_fall_through_err")

        # Additional child outputs make state-leaf wiring observable. / 额外子级输出使状态叶连线可观测。
        self.ftb_entry_valid = Signal(name="io_ftb_entry_valid")
        self.ftb_entry_jmp_taken = Signal(name="io_ftb_entry_jmp_taken")
        self.compare_least = Signal(4, name="io_compare_least")
        self.saturate_value = Signal(2, name="io_saturate_value")
        self.signed_saturate_value = Signal(2, name="io_signed_saturate_value")
        self.replacer_victim = Signal(2, name="io_replacer_victim")
        self.wr_bypass_hit = Signal(name="io_wr_bypass_hit")

        # Explicit injection points; no sibling Build imports are used. / 显式注入点，不导入其他 Build。
        self.fau_ftb_way = deps.get("fau_ftb_way") or deps.get("FauFTBWay") or BpuNullChild()
        self.fallthrough = deps.get("fallthrough") or deps.get("FallThroughPredictor") or BpuNullChild()
        self.ftb_entry_gen = deps.get("ftb_entry_gen") or deps.get("FTBEntryGen") or BpuNullChild()
        self.compare_matrix = deps.get("compare_matrix") or deps.get("CompareMatrix") or BpuNullChild()
        self.saturate_counter = deps.get("saturate_counter") or deps.get("SaturateCounter") or BpuNullChild()
        self.signed_saturate_counter = deps.get("signed_saturate_counter") or deps.get("SignedSaturateCounter") or BpuNullChild()
        self.replacer = deps.get("replacer") or deps.get("ReplacerState") or BpuNullChild()
        self.wr_bypass = deps.get("wr_bypass") or deps.get("WrBypass") or BpuNullChild()

    # Connect one assignable child signal, preserving fallback tie-offs. / 连接可赋值的子级信号并保留回退置零。
    def connect(self, module: Module, child: Any, child_attr: str, parent_signal: Any) -> None:
        """Drive a child input when its canonical signal exists. / 若存在标准信号则驱动子级输入。"""
        signal = getattr(child, child_attr, None)
        if isinstance(signal, Signal):
            module.d.comb += signal.eq(parent_signal)

    # Forward one child output or a deterministic zero. / 转发子级输出或确定性零值。
    def forward(self, module: Module, child: Any, child_attr: str, parent_signal: Signal) -> None:
        """Expose a child output when present. / 存在时导出子级输出。"""
        signal = getattr(child, child_attr, None)
        if isinstance(signal, Signal):
            module.d.comb += parent_signal.eq(signal)
        else:
            module.d.comb += parent_signal.eq(0)

    # Elaborate the complete bounded child wiring. / 展开完整的有界子级连线。
    def elaborate(self, platform: Any) -> Module:
        """Instantiate and connect all injected BPU leaves. / 实例化并连接所有注入的 BPU 叶子。"""
        del platform
        m = Module()
        children = (("fau_ftb_way", self.fau_ftb_way), ("fallthrough", self.fallthrough),
                    ("ftb_entry_gen", self.ftb_entry_gen), ("compare_matrix", self.compare_matrix),
                    ("saturate_counter", self.saturate_counter),
                    ("signed_saturate_counter", self.signed_saturate_counter),
                    ("replacer", self.replacer), ("wr_bypass", self.wr_bypass))
        for name, child in children:
            setattr(m.submodules, name, child)
        # Clock/reset are real parent-to-child wires for every sequential leaf.
        # 时钟/复位是所有时序叶子的真实父子连线。
        for child in (self.fau_ftb_way, self.fallthrough, self.ftb_entry_gen,
                      self.compare_matrix, self.saturate_counter,
                      self.signed_saturate_counter, self.replacer, self.wr_bypass):
            self.connect(m, child, "clock", self.clock)
            self.connect(m, child, "reset", self.reset)

        # FauFTBWay exact request/update payload wiring. / FauFTBWay 精确请求/更新字段连线。
        fau_pairs = {
            "req_tag": self.req_tag, "update_req_tag": self.update_req_tag,
            "write_valid": self.write_valid, "write_tag": self.write_tag,
            "write_is_call": self.write_entry_is_call, "write_is_ret": self.write_entry_is_ret,
            "write_is_jalr": self.write_entry_is_jalr, "write_entry_valid": self.write_entry_valid,
            "write_br_offset": self.write_br_offset, "write_br_sharing": self.write_br_sharing,
            "write_br_valid": self.write_br_valid, "write_br_lower": self.write_br_lower,
            "write_br_tar_stat": self.write_br_tar_stat, "write_tail_offset": self.write_tail_offset,
            "write_tail_sharing": self.write_tail_sharing, "write_tail_valid": self.write_tail_valid,
            "write_tail_lower": self.write_tail_lower, "write_tail_tar_stat": self.write_tail_tar_stat,
            "write_pft_addr": self.write_pft_addr, "write_carry": self.write_carry,
            "write_last_rvi_call": self.write_last_rvi_call,
            "write_strong_bias_0": self.write_strong_bias_0, "write_strong_bias_1": self.write_strong_bias_1,
        }
        for child_attr, parent_signal in fau_pairs.items():
            self.connect(m, self.fau_ftb_way, child_attr, parent_signal)
        for child_attr, parent_signal in {
            "resp_is_call": self.resp_is_call, "resp_is_ret": self.resp_is_ret,
            "resp_is_jalr": self.resp_is_jalr, "resp_valid": self.resp_valid,
            "resp_br_offset": self.resp_br_offset, "resp_br_sharing": self.resp_br_sharing,
            "resp_br_valid": self.resp_br_valid, "resp_br_lower": self.resp_br_lower,
            "resp_br_tar_stat": self.resp_br_tar_stat, "resp_tail_offset": self.resp_tail_offset,
            "resp_tail_sharing": self.resp_tail_sharing, "resp_tail_valid": self.resp_tail_valid,
            "resp_tail_lower": self.resp_tail_lower, "resp_tail_tar_stat": self.resp_tail_tar_stat,
            "resp_pft_addr": self.resp_pft_addr, "resp_carry": self.resp_carry,
            "resp_last_rvi_call": self.resp_last_rvi_call,
            "resp_strong_bias_0": self.resp_strong_bias_0, "resp_strong_bias_1": self.resp_strong_bias_1,
            "resp_hit": self.resp_hit, "update_hit": self.update_hit,
        }.items():
            self.forward(m, self.fau_ftb_way, child_attr, parent_signal)

        # Fall-through child receives the same parent PC/entry stage. / 顺序落空子级接收同一父级 PC/条目阶段。
        for child_attr, parent_signal in {
            "enable": self.enable[0], "reset_vector": self.reset_vector, "start_pc": self.start_pc,
            "carry": self.carry, "pft_addr": self.pft_addr, "entry_valid": self.entry_valid,
            "hit": self.entry_hit, "s0_fire": self.s0_fire, "s1_fire": self.s1_fire,
        }.items():
            self.connect(m, self.fallthrough, child_attr, parent_signal)
        for child_attr, parent_signal in {
            "pred_taken": self.pred_taken, "pred_target": self.pred_target,
            "pred_cfi_position": self.pred_cfi_position, "fall_through_addr": self.fall_through_addr,
            "fall_through_err": self.fall_through_err,
        }.items():
            self.forward(m, self.fallthrough, child_attr, parent_signal)

        # FTBEntryGen is connected to the live Fau/FallThrough observations.
        # FTBEntryGen 连接到实时 Fau/FallThrough 观测，形成可追踪子级路径。
        self.connect(m, self.ftb_entry_gen, "start_addr", self.start_pc)
        self.connect(m, self.ftb_entry_gen, "target", self.pred_target)
        self.connect(m, self.ftb_entry_gen, "hit", self.resp_hit)
        self.connect(m, self.ftb_entry_gen, "old_valid", self.resp_valid)
        self.forward(m, self.ftb_entry_gen, "new_valid", self.ftb_entry_valid)
        self.forward(m, self.ftb_entry_gen, "jmp_taken", self.ftb_entry_jmp_taken)

        # State leaves are intentionally small but live: their enables/inputs
        # derive from the same request/update transaction rather than constants.
        # 状态叶保持小而真实：使能/输入来自同一请求/更新事务，而非常量。
        self.connect(m, self.saturate_counter, "en", self.write_valid)
        self.connect(m, self.saturate_counter, "increase", self.write_entry_valid)
        self.forward(m, self.saturate_counter, "value", self.saturate_value)
        self.connect(m, self.signed_saturate_counter, "en", self.write_valid)
        self.connect(m, self.signed_saturate_counter, "positive", self.write_entry_valid)
        self.forward(m, self.signed_saturate_counter, "value", self.signed_saturate_value)
        self.forward(m, self.replacer, "victim_way", self.replacer_victim)
        self.forward(m, self.wr_bypass, "hit", self.wr_bypass_hit)
        self.forward(m, self.compare_matrix, "least_element_oh", self.compare_least)
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Emit a stable project-facing aggregate name. / 导出稳定的项目侧聚合名称。
def build_verilog(configuration, injected_dependencies):
    """Return BPU parent RTL with injected child modules. / 返回带注入子级的 BPU 父级 RTL。"""
    cfg = configuration if isinstance(configuration, BpuParentConfig) else BpuParentConfig()
    top = BpuParent(cfg, injected_dependencies if isinstance(injected_dependencies, dict) else {})
    ports = [signal for signal in vars(top).values() if isinstance(signal, Signal)]
    # Preserve deterministic declaration order and remove duplicate aliases.
    unique: list[Signal] = []
    seen: set[int] = set()
    for signal in ports:
        if id(signal) not in seen:
            unique.append(signal)
            seen.add(id(signal))
    return verilog.convert(top, name="UHSCBpuParent", ports=unique)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> int:
    """Emit standalone BPU parent RTL. / 导出独立 BPU 父级 RTL。"""
    print(build_verilog(None, {}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
