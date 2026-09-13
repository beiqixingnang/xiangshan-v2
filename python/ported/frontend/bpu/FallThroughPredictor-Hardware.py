"""Fall-through predictor of XiangShan BPU (next-block / next-page fall-through pc).
香山 BPU 顺序执行（fall-through）预测器的 amaranth 重写。
"""

from __future__ import annotations

from dataclasses import dataclass

from amaranth import C, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# ============================================================================
# Module Contract
# ============================================================================
# Public symbols / 公开符号:
#   FallThroughPredictor - BasePredictor-style module: s0 startPc -> s1 prediction
#     outputs: pred_taken(=0), pred_cfi_position, pred_target, pred_attribute(=None)
#   build_verilog / main
# Contract: s0_fire registers startPc; s1 computes aligned next block pc, cross-page
# fix to next page boundary, and cfi position (FetchBlockInstNum-1 or page-fix).
# depends on Build-Cpu.Frontend.Bpu.Helpers (align/cross-page helpers 内联实现于此)
__all__ = [
    "FallThroughConfig",
    "FallThroughPredictor",
    "build_verilog",
    "main",
]


# ============================================================================
# Configuration
# ============================================================================
@dataclass(frozen=True)
class FallThroughConfig:
    # Fall-through geometry config / 顺序预测几何配置
    guarded_vaddr_bits: int = 40
    fetch_block_size: int = 64               # bytes (PrunedAddr stores halfword units)
    fetch_block_align_width: int = 5         # log2(32B) in byte-address space / 字节地址空间中的 32B 对齐
    cfi_position_width: int = 5
    page_offset_width: int = 12
    inst_offset_bits: int = 1

    # FetchBlockInstNum - 1 (constant cfi position when not crossing page)
    # 不跨页时的常量 cfi 位置（块内指令数减一）
    @property
    # last_inst_position responsibility. / last_inst_position 函数职责。
    def last_inst_position(self) -> int:
        return self.fetch_block_size // 2 - 1  # 2B per inst slot / 每槽 2 字节


# ============================================================================
# Implementation
# ============================================================================
class FallThroughPredictor(Elaboratable):
    # Fall-through predictor (s0 -> s1) / 顺序预测器（s0 到 s1）
    def __init__(self, config: FallThroughConfig = FallThroughConfig()) -> None:
        super().__init__()
        self.config = config
        vb = config.guarded_vaddr_bits
        # control / 控制
        self.enable = Signal()
        self.s0_fire = Signal()
        self.s1_fire = Signal()
        self.start_pc = Signal(vb)
        self.train_ready = Signal()
        self.sram_reset_done = Signal()
        # prediction outputs / 预测输出
        self.pred_taken = Signal()
        self.pred_cfi_position = Signal(config.cfi_position_width)
        self.pred_target = Signal(vb)
        self.pred_cross_page = Signal()

    # Cat helper for alignment / 对齐拼接助手
    def cat_align(self, pc):
        from amaranth import Cat

        cfg = self.config
        # PrunedAddr omits instOffsetBits low address bits; align the encoded
        # field by the remaining byte-alignment bits. / PrunedAddr 去掉低位
        # 指令偏移位，因此只清除剩余的字节对齐位。
        align_bits = cfg.fetch_block_align_width - cfg.inst_offset_bits
        return Cat(C(0, align_bits), pc[align_bits:])

    # Elaborate s0 register + s1 fall-through computation / 展开 s0 寄存与 s1 顺序地址计算
    def elaborate(self, platform) -> Module:
        from amaranth import Cat

        m = Module()
        cfg = self.config
        vb = cfg.guarded_vaddr_bits

        m.d.comb += [self.train_ready.eq(1), self.sram_reset_done.eq(1)]

        # s1_startPc register / s1 起始 PC 寄存器
        s1_start_pc = Signal(vb)
        with m.If(self.s0_fire):
            m.d.sync += s1_start_pc.eq(self.start_pc)

        # fall-through encoded address = startPc + FetchBlockSize / 2, aligned
        # to the encoded FetchBlockAlign. / 顺序编码地址加半字节单位的块长。
        # 顺序地址 = 起始 PC + 取指块大小，再按对齐尺寸对齐
        next_block_pc = (s1_start_pc + (cfg.fetch_block_size >> cfg.inst_offset_bits))[:vb]
        s1_next_block_aligned_pc = self.cat_align(next_block_pc)[:vb]

        # cross page check: compare LSB of VPN / 跨页检查：比较页号最低位
        po = cfg.page_offset_width - cfg.inst_offset_bits
        s1_cross_page = s1_start_pc[po] != s1_next_block_aligned_pc[po]
        s1_next_page_aligned_pc = Cat(C(0, po), s1_next_block_aligned_pc[po:])[:vb]

        # cfiPosition: constant when not crossing page; else page-fix complement
        # cfi 位置：不跨页为常量，跨页取补码修正
        w = cfg.cfi_position_width
        # Scala slices the full byte address at [w+instOffsetBits-1:instOffsetBits].
        # On the encoded PrunedAddr field this is simply [w-1:0]. /
        diff = (s1_next_block_aligned_pc - s1_next_page_aligned_pc)[:w]
        s1_cfi_position = Mux(s1_cross_page, ~diff, C(cfg.last_inst_position, w))

        s1_fall_through_pc = Mux(s1_cross_page, s1_next_page_aligned_pc, s1_next_block_aligned_pc)

        m.d.comb += [
            self.pred_taken.eq(0),
            self.pred_cfi_position.eq(s1_cfi_position),
            self.pred_target.eq(s1_fall_through_pc),
            self.pred_cross_page.eq(s1_cross_page),
        ]
        return m


# ============================================================================
# Public Adapter
# ============================================================================
# Build Verilog for the fall-through predictor / 为顺序预测器生成 Verilog
def build_verilog(config: FallThroughConfig = FallThroughConfig()) -> str:
    top = FallThroughPredictor(config)
    ports = [
        top.enable, top.s0_fire, top.s1_fire, top.start_pc,
        top.train_ready, top.sram_reset_done,
        top.pred_taken, top.pred_cfi_position, top.pred_target, top.pred_cross_page,
    ]
    return verilog.convert(top, ports=ports)


# ============================================================================
# Direct Entry
# ============================================================================
# Direct entry: print generated Verilog / 直接入口：打印生成的 Verilog
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
