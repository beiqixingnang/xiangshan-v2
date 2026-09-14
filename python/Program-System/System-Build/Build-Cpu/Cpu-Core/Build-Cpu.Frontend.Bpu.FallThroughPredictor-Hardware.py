"""V2 FTB fall-through address closure. / V2 FTB 顺序地址闭包。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# V2 distributes fall-through behavior across BPUUtils.getFallThroughAddr,
# FTBEntry.getFallThrough, and FullBranchPrediction.fromFtbEntry. This leaf
# models the shared address/error equations and registers the request once to
# provide the two-stage observation point used by the frontend closure.
# V2 将顺序地址行为分布在 BPU/FTB/FrontendBundle；本叶复现共享地址与错误方程。
__all__ = [
    "FallThroughConfig",
    "FallThroughPredictor",
    "fall_through_address",
    "fall_through_error",
    "fall_through_target",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class FallThroughConfig:
    """Describe V2 fetch geometry. / 描述 V2 取指几何参数。"""

    vaddr_bits: int = 39
    predict_width: int = 16
    fetch_width: int = 8
    inst_offset_bits: int = 1
    page_offset_bits: int = 12
    # Historical names remain as explicit configuration fields. / 保留历史字段名。
    guarded_vaddr_bits: int | None = None
    fetch_block_size: int | None = None
    fetch_block_align_width: int | None = None
    cfi_position_width: int | None = None
    page_offset_width: int | None = None

    # Validate fetch geometry and resolve compatibility defaults. / 校验并解析兼容几何参数。
    def __post_init__(self) -> None:
        if self.vaddr_bits < 4:
            raise ValueError("virtual address width is too small")
        if self.predict_width < 1 or self.predict_width & (self.predict_width - 1):
            raise ValueError("predict width must be a positive power of two")
        if self.fetch_width < 1:
            raise ValueError("fetch width must be positive")
        if self.inst_offset_bits < 0:
            raise ValueError("instruction offset width must be non-negative")
        if self.page_offset_bits <= self.inst_offset_bits:
            raise ValueError("page offset must exceed instruction offset")
        if self.page_offset_width is not None and self.page_offset_width <= self.inst_offset_bits:
            raise ValueError("page_offset_width must exceed instruction offset")
        if self.fetch_block_size is not None and self.fetch_block_size < 1:
            raise ValueError("fetch block size must be positive")

    # Return the effective virtual-address width. / 返回有效虚拟地址宽度。
    @property
    # effective_vaddr_bits responsibility. / effective_vaddr_bits 函数职责。
    def effective_vaddr_bits(self) -> int:
        return self.guarded_vaddr_bits or self.vaddr_bits

    # Return the effective page-offset width. / 返回有效页内偏移宽度。
    @property
    # effective_page_offset_bits responsibility. / effective_page_offset_bits 函数职责。
    def effective_page_offset_bits(self) -> int:
        return self.page_offset_width or self.page_offset_bits

    # Return the width of the partial fall-through address. / 返回部分顺序地址宽度。
    @property
    # pft_width responsibility. / pft_width 函数职责。
    def pft_width(self) -> int:
        return max(1, (self.predict_width - 1).bit_length())

    # Return the width of the carry-qualified lower field. / 返回带进位低位域宽度。
    @property
    # lower_width responsibility. / lower_width 函数职责。
    def lower_width(self) -> int:
        return self.pft_width + 1

    # Return the legacy cfi-position width. / 返回历史 cfi 位置宽度。
    @property
    # effective_cfi_position_width responsibility. / effective_cfi_position_width 函数职责。
    def effective_cfi_position_width(self) -> int:
        return self.cfi_position_width or self.pft_width

    # Return the legacy final instruction slot position. / 返回历史末指令槽位置。
    @property
    # last_inst_position responsibility. / last_inst_position 函数职责。
    def last_inst_position(self) -> int:
        if self.fetch_block_size is not None:
            return self.fetch_block_size // (1 << self.inst_offset_bits) - 1
        return self.predict_width - 1


# =============================================================================
# Implementation
# =============================================================================
# Compute BPUUtils.getFallThroughAddr in integers. / 整数域计算 BPUUtils 顺序地址。
def fall_through_address(start: int, carry: bool, pft_addr: int,
                         configuration: FallThroughConfig | None = None) -> int:
    """Compose a V2 FTB fall-through address. / 组合 V2 FTB 顺序地址。"""

    cfg = configuration or FallThroughConfig()
    bits = cfg.effective_vaddr_bits
    pft_width = cfg.pft_width
    lower_shift = cfg.inst_offset_bits
    higher_shift = lower_shift + pft_width
    mask = (1 << bits) - 1
    start &= mask
    pft_addr &= (1 << pft_width) - 1
    higher = start >> higher_shift
    if carry:
        higher = (higher + 1) & ((1 << (bits - higher_shift)) - 1)
    return ((higher << (pft_width + lower_shift)) |
            (pft_addr << lower_shift)) & mask


# Compute FrontendBundle's lower-field fall-through error. / 计算 FrontendBundle 低位顺序错误。
def fall_through_error(pc: int, carry: bool, pft_addr: int,
                       configuration: FallThroughConfig | None = None) -> bool:
    """Check whether an FTB entry ends outside the fetch block. / 检查 FTB 条目是否越界。"""

    cfg = configuration or FallThroughConfig()
    pft_width = cfg.pft_width
    lower_shift = cfg.inst_offset_bits
    start_lower = (pc >> lower_shift) & ((1 << pft_width) - 1)
    end_lower = ((int(bool(carry)) << pft_width) |
                 (pft_addr & ((1 << pft_width) - 1)))
    return start_lower >= end_lower or end_lower > start_lower + cfg.predict_width


# Select the fallback target used by FullBranchPrediction. / 选择 FullBranchPrediction 的回退目标。
def fall_through_target(pc: int, carry: bool, pft_addr: int,
                        entry_valid: bool = True, hit: bool = True,
                        configuration: FallThroughConfig | None = None) -> tuple[int, bool]:
    """Return ``(target, error)`` at the V2 observation point. / 返回 V2 观察点的目标与错误。"""

    cfg = configuration or FallThroughConfig()
    mask = (1 << cfg.effective_vaddr_bits) - 1
    error = fall_through_error(pc, carry, pft_addr, cfg)
    # FullBranchPrediction exposes the error independently; a miss or invalid
    # entry takes the sequential fetch-width target.
    fallback = (pc + cfg.fetch_width * 4) & mask
    target = fall_through_address(pc, carry, pft_addr, cfg)
    if error or not entry_valid or not hit:
        target = fallback
    return target, bool(error and hit)


class FallThroughPredictor(Elaboratable):
    """Two-stage FTB fall-through closure. / 两级 FTB 顺序地址闭包。"""

    # Declare request, entry, and prediction ports. / 声明请求、条目与预测端口。
    def __init__(self, configuration: FallThroughConfig | None = None) -> None:
        self.configuration = configuration or FallThroughConfig()
        cfg = self.configuration
        bits = cfg.effective_vaddr_bits
        self.enable = Signal(name="enable")
        self.s0_fire = Signal(name="s0_fire")
        self.s1_fire = Signal(name="s1_fire")
        self.start_pc = Signal(bits, name="start_pc")
        self.carry = Signal(name="carry")
        self.pft_addr = Signal(cfg.pft_width, name="pft_addr")
        self.entry_valid = Signal(name="entry_valid")
        self.hit = Signal(name="hit")
        self.train_ready = Signal(name="train_ready")
        self.sram_reset_done = Signal(name="sram_reset_done")
        self.pred_taken = Signal(name="pred_taken")
        self.pred_cfi_position = Signal(cfg.effective_cfi_position_width, name="pred_cfi_position")
        self.pred_target = Signal(bits, name="pred_target")
        self.pred_cross_page = Signal(name="pred_cross_page")
        self.fall_through_addr = Signal(bits, name="fall_through_addr")
        self.fall_through_err = Signal(name="fall_through_err")

    # Align an encoded address to the configured fetch block. / 将编码地址对齐到配置的取指块。
    def cat_align(self, pc: Any) -> Any:
        align_width = self.configuration.fetch_block_align_width
        if align_width is None:
            align_width = self.configuration.inst_offset_bits + self.configuration.pft_width
        clear = max(0, align_width - self.configuration.inst_offset_bits)
        return (pc >> clear) << clear

    # Elaborate the staged V2 address/error equations. / 展开分级 V2 地址与错误方程。
    def elaborate(self, platform: Any) -> Module:
        del platform
        cfg = self.configuration
        bits = cfg.effective_vaddr_bits
        module = Module()
        pc_reg = Signal(bits, name="s1_pc")
        carry_reg = Signal(name="s1_carry")
        pft_reg = Signal(cfg.pft_width, name="s1_pft_addr")
        valid_reg = Signal(name="s1_entry_valid")
        hit_reg = Signal(name="s1_hit")
        with module.If(self.s0_fire):
            module.d.sync += [
                pc_reg.eq(self.start_pc),
                carry_reg.eq(self.carry),
                pft_reg.eq(self.pft_addr),
                valid_reg.eq(self.entry_valid),
                hit_reg.eq(self.hit),
            ]

        higher_shift = cfg.inst_offset_bits + cfg.pft_width
        higher = pc_reg[higher_shift:bits]
        higher_plus = (higher + Const(1, len(higher)))[: len(higher)]
        selected_higher = Mux(carry_reg, higher_plus, higher)
        composed = (selected_higher << (cfg.pft_width + cfg.inst_offset_bits))
        composed = composed | (pft_reg << cfg.inst_offset_bits)
        composed = composed[:bits]
        start_lower = pc_reg[cfg.inst_offset_bits:cfg.inst_offset_bits + cfg.pft_width]
        end_lower = (carry_reg << cfg.pft_width) | pft_reg
        lower_error = (start_lower >= end_lower) | (end_lower > start_lower + Const(cfg.predict_width, cfg.lower_width))
        sequential = (pc_reg + Const(cfg.fetch_width * 4, bits))[:bits]
        target = Mux(lower_error | ~valid_reg | ~hit_reg, sequential, composed)
        # A carry indicates the FTB target moved to the next partial page. / carry 表示跨越高位块。
        cross_page = carry_reg
        cfi_width = cfg.effective_cfi_position_width
        cfi_value = pft_reg[:cfi_width] if cfg.pft_width >= cfi_width else pft_reg
        module.d.comb += [
            self.train_ready.eq(1),
            self.sram_reset_done.eq(1),
            self.pred_taken.eq(0),
            self.fall_through_addr.eq(composed),
            self.fall_through_err.eq(lower_error),
            self.pred_target.eq(target),
            self.pred_cross_page.eq(cross_page),
            self.pred_cfi_position.eq(cfi_value),
        ]
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Emit deterministic RTL for the fall-through closure. / 输出顺序地址闭包 RTL。
def build_verilog(configuration, injected_dependencies):
    del injected_dependencies
    top = FallThroughPredictor(configuration)
    return verilog.convert(
        top,
        name="FallThroughPredictor",
        ports=[top.enable, top.s0_fire, top.s1_fire, top.start_pc,
               top.carry, top.pft_addr, top.entry_valid, top.hit,
               top.train_ready, top.sram_reset_done, top.pred_taken,
               top.pred_cfi_position, top.pred_target, top.pred_cross_page,
               top.fall_through_addr, top.fall_through_err],
        emit_src=False,
    )


# =============================================================================
# Direct Entry
# =============================================================================
# Print generated RTL for a default closure. / 打印默认顺序地址闭包 RTL。
def main() -> None:
    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
