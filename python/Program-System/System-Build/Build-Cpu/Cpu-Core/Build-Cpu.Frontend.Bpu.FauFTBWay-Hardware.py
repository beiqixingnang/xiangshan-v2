"""V2 fast auxiliary FTB way with tag and write-bypass behavior.
V2 快速辅助 FTB 单路标签与写旁路行为。
"""

from __future__ import annotations
# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false, reportOperatorIssue=false

from dataclasses import dataclass

from amaranth import ClockDomain, Elaboratable, Module, Signal


# Module Contract
# ---------------------------------------------------------------------------
# FauFTBWay stores one fast-target-buffer entry and compares request/update
# tags while allowing a pending write to bypass the update lookup.
# FauFTBWay 保存一个快速目标缓冲条目，比较请求/更新标签并旁路待写更新查找。
__all__ = ["FauFTBWayConfig", "FauFTBWay", "build_verilog", "main"]


# Configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FauFTBWayConfig:
    """V2 FauFTB entry field widths. / V2 FauFTB 条目字段位宽。"""

    tag_width: int = 16
    branch_offset_width: int = 4
    branch_lower_width: int = 12
    target_offset_width: int = 20
    target_status_width: int = 2
    prefetch_address_width: int = 4

    # Validate the fixed V2 field geometry. / 校验固定 V2 字段几何。
    def __post_init__(self) -> None:
        if min(
            self.tag_width,
            self.branch_offset_width,
            self.branch_lower_width,
            self.target_offset_width,
            self.target_status_width,
            self.prefetch_address_width,
        ) < 1:
            raise ValueError("all FauFTBWay widths must be positive")


# Implementation
# ---------------------------------------------------------------------------
class FauFTBWay(Elaboratable):
    """Single registered FTB way with V2 hit equations. / 带 V2 命中方程的单路寄存式 FTB。"""

    # Construct exact locked-reference ports and entry fields.
    # 构造与锁定参考完全一致的端口及条目字段。 /
    def __init__(self, configuration: FauFTBWayConfig = FauFTBWayConfig()) -> None:
        self.configuration = configuration
        c = configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.clock_domain = ClockDomain("sync", async_reset=True)
        self.clock_domain.clk = self.clock
        self.clock_domain.rst = self.reset

        self.req_tag = Signal(c.tag_width, name="io_req_tag")
        self.resp_is_call = Signal(name="io_resp_isCall")
        self.resp_is_ret = Signal(name="io_resp_isRet")
        self.resp_is_jalr = Signal(name="io_resp_isJalr")
        self.resp_valid = Signal(name="io_resp_valid")
        self.resp_br_offset = Signal(c.branch_offset_width, name="io_resp_brSlots_0_offset")
        self.resp_br_sharing = Signal(name="io_resp_brSlots_0_sharing")
        self.resp_br_valid = Signal(name="io_resp_brSlots_0_valid")
        self.resp_br_lower = Signal(c.branch_lower_width, name="io_resp_brSlots_0_lower")
        self.resp_br_tar_stat = Signal(c.target_status_width, name="io_resp_brSlots_0_tarStat")
        self.resp_tail_offset = Signal(c.branch_offset_width, name="io_resp_tailSlot_offset")
        self.resp_tail_sharing = Signal(name="io_resp_tailSlot_sharing")
        self.resp_tail_valid = Signal(name="io_resp_tailSlot_valid")
        self.resp_tail_lower = Signal(c.target_offset_width, name="io_resp_tailSlot_lower")
        self.resp_tail_tar_stat = Signal(c.target_status_width, name="io_resp_tailSlot_tarStat")
        self.resp_pft_addr = Signal(c.prefetch_address_width, name="io_resp_pftAddr")
        self.resp_carry = Signal(name="io_resp_carry")
        self.resp_last_rvi_call = Signal(name="io_resp_last_may_be_rvi_call")
        self.resp_strong_bias_0 = Signal(name="io_resp_strong_bias_0")
        self.resp_strong_bias_1 = Signal(name="io_resp_strong_bias_1")
        self.resp_hit = Signal(name="io_resp_hit")

        self.update_req_tag = Signal(c.tag_width, name="io_update_req_tag")
        self.update_hit = Signal(name="io_update_hit")
        self.write_valid = Signal(name="io_write_valid")
        self.write_is_call = Signal(name="io_write_entry_isCall")
        self.write_is_ret = Signal(name="io_write_entry_isRet")
        self.write_is_jalr = Signal(name="io_write_entry_isJalr")
        self.write_entry_valid = Signal(name="io_write_entry_valid")
        self.write_br_offset = Signal(c.branch_offset_width, name="io_write_entry_brSlots_0_offset")
        self.write_br_sharing = Signal(name="io_write_entry_brSlots_0_sharing")
        self.write_br_valid = Signal(name="io_write_entry_brSlots_0_valid")
        self.write_br_lower = Signal(c.branch_lower_width, name="io_write_entry_brSlots_0_lower")
        self.write_br_tar_stat = Signal(c.target_status_width, name="io_write_entry_brSlots_0_tarStat")
        self.write_tail_offset = Signal(c.branch_offset_width, name="io_write_entry_tailSlot_offset")
        self.write_tail_sharing = Signal(name="io_write_entry_tailSlot_sharing")
        self.write_tail_valid = Signal(name="io_write_entry_tailSlot_valid")
        self.write_tail_lower = Signal(c.target_offset_width, name="io_write_entry_tailSlot_lower")
        self.write_tail_tar_stat = Signal(c.target_status_width, name="io_write_entry_tailSlot_tarStat")
        self.write_pft_addr = Signal(c.prefetch_address_width, name="io_write_entry_pftAddr")
        self.write_carry = Signal(name="io_write_entry_carry")
        self.write_last_rvi_call = Signal(name="io_write_entry_last_may_be_rvi_call")
        self.write_strong_bias_0 = Signal(name="io_write_entry_strong_bias_0")
        self.write_strong_bias_1 = Signal(name="io_write_entry_strong_bias_1")
        self.write_tag = Signal(c.tag_width, name="io_write_tag")

    # Elaborate registered entry storage, tag compares, and write bypass.
    # 展开寄存式条目存储、标签比较及写旁路。 /
    def elaborate(self, platform) -> Module:
        del platform
        m = Module()
        m.domains += self.clock_domain
        c = self.configuration

        data_is_call = Signal(name="data_isCall")
        data_is_ret = Signal(name="data_isRet")
        data_is_jalr = Signal(name="data_isJalr")
        data_valid = Signal(name="data_valid")
        data_br_offset = Signal(c.branch_offset_width, name="data_brSlots_0_offset")
        data_br_sharing = Signal(name="data_brSlots_0_sharing")
        data_br_valid = Signal(name="data_brSlots_0_valid")
        data_br_lower = Signal(c.branch_lower_width, name="data_brSlots_0_lower")
        data_br_tar_stat = Signal(c.target_status_width, name="data_brSlots_0_tarStat")
        data_tail_offset = Signal(c.branch_offset_width, name="data_tailSlot_offset")
        data_tail_sharing = Signal(name="data_tailSlot_sharing")
        data_tail_valid = Signal(name="data_tailSlot_valid")
        data_tail_lower = Signal(c.target_offset_width, name="data_tailSlot_lower")
        data_tail_tar_stat = Signal(c.target_status_width, name="data_tailSlot_tarStat")
        data_pft_addr = Signal(c.prefetch_address_width, name="data_pftAddr")
        data_carry = Signal(name="data_carry")
        data_last_rvi_call = Signal(name="data_last_may_be_rvi_call")
        data_strong_bias_0 = Signal(name="data_strong_bias_0")
        data_strong_bias_1 = Signal(name="data_strong_bias_1")
        tag = Signal(c.tag_width, name="tag")
        valid = Signal(name="valid", reset=0)

        # The response is a direct view of the stored FTB entry.
        # 响应是存储 FTB 条目的直接视图。
        m.d.comb += [
            self.resp_is_call.eq(data_is_call),
            self.resp_is_ret.eq(data_is_ret),
            self.resp_is_jalr.eq(data_is_jalr),
            self.resp_valid.eq(data_valid),
            self.resp_br_offset.eq(data_br_offset),
            self.resp_br_sharing.eq(data_br_sharing),
            self.resp_br_valid.eq(data_br_valid),
            self.resp_br_lower.eq(data_br_lower),
            self.resp_br_tar_stat.eq(data_br_tar_stat),
            self.resp_tail_offset.eq(data_tail_offset),
            self.resp_tail_sharing.eq(data_tail_sharing),
            self.resp_tail_valid.eq(data_tail_valid),
            self.resp_tail_lower.eq(data_tail_lower),
            self.resp_tail_tar_stat.eq(data_tail_tar_stat),
            self.resp_pft_addr.eq(data_pft_addr),
            self.resp_carry.eq(data_carry),
            self.resp_last_rvi_call.eq(data_last_rvi_call),
            self.resp_strong_bias_0.eq(data_strong_bias_0),
            self.resp_strong_bias_1.eq(data_strong_bias_1),
            self.resp_hit.eq((tag == self.req_tag) & valid),
            self.update_hit.eq(((tag == self.update_req_tag) & valid) | (self.write_tag == self.update_req_tag) & self.write_valid),
        ]

        # A write captures every entry field and sets valid monotonically.
        # 写入捕获全部条目字段，并单调置有效位。
        with m.If(self.write_valid):
            m.d.sync += [
                data_is_call.eq(self.write_is_call),
                data_is_ret.eq(self.write_is_ret),
                data_is_jalr.eq(self.write_is_jalr),
                data_valid.eq(self.write_entry_valid),
                data_br_offset.eq(self.write_br_offset),
                data_br_sharing.eq(self.write_br_sharing),
                data_br_valid.eq(self.write_br_valid),
                data_br_lower.eq(self.write_br_lower),
                data_br_tar_stat.eq(self.write_br_tar_stat),
                data_tail_offset.eq(self.write_tail_offset),
                data_tail_sharing.eq(self.write_tail_sharing),
                data_tail_valid.eq(self.write_tail_valid),
                data_tail_lower.eq(self.write_tail_lower),
                data_tail_tar_stat.eq(self.write_tail_tar_stat),
                data_pft_addr.eq(self.write_pft_addr),
                data_carry.eq(self.write_carry),
                data_last_rvi_call.eq(self.write_last_rvi_call),
                data_strong_bias_0.eq(self.write_strong_bias_0),
                data_strong_bias_1.eq(self.write_strong_bias_1),
                tag.eq(self.write_tag),
            ]
        with m.If(self.write_valid & ~valid):
            m.d.sync += valid.eq(1)
        return m


# Public Adapter
# ---------------------------------------------------------------------------
# Emit the exact default FauFTBWay specialization used by locked XSTop.
# 导出锁定 XSTop 使用的精确默认 FauFTBWay 特化。


# Build standalone Verilog with locked V2 port names.
# 使用锁定 V2 端口名构建独立 Verilog。 /
def build_verilog(configuration, injected_dependencies):
    """Return generated FauFTBWay RTL. / 返回生成的 FauFTBWay RTL。"""

    del injected_dependencies
    from amaranth.back import verilog

    config = configuration if isinstance(configuration, FauFTBWayConfig) else FauFTBWayConfig()
    top = FauFTBWay(config)
    ports = [
        top.clock,
        top.reset,
        top.req_tag,
        top.resp_is_call,
        top.resp_is_ret,
        top.resp_is_jalr,
        top.resp_valid,
        top.resp_br_offset,
        top.resp_br_sharing,
        top.resp_br_valid,
        top.resp_br_lower,
        top.resp_br_tar_stat,
        top.resp_tail_offset,
        top.resp_tail_sharing,
        top.resp_tail_valid,
        top.resp_tail_lower,
        top.resp_tail_tar_stat,
        top.resp_pft_addr,
        top.resp_carry,
        top.resp_last_rvi_call,
        top.resp_strong_bias_0,
        top.resp_strong_bias_1,
        top.resp_hit,
        top.update_req_tag,
        top.update_hit,
        top.write_valid,
        top.write_is_call,
        top.write_is_ret,
        top.write_is_jalr,
        top.write_entry_valid,
        top.write_br_offset,
        top.write_br_sharing,
        top.write_br_valid,
        top.write_br_lower,
        top.write_br_tar_stat,
        top.write_tail_offset,
        top.write_tail_sharing,
        top.write_tail_valid,
        top.write_tail_lower,
        top.write_tail_tar_stat,
        top.write_pft_addr,
        top.write_carry,
        top.write_last_rvi_call,
        top.write_strong_bias_0,
        top.write_strong_bias_1,
        top.write_tag,
    ]
    return verilog.convert(top, ports=ports, name="FauFTBWay")


# Direct Entry
# ---------------------------------------------------------------------------
# Print deterministic default RTL for command-line smoke tests.
# 打印确定性的默认 RTL 以支持命令行冒烟测试。


# Print generated default Verilog. / 打印生成的默认 Verilog。
def main() -> None:
    """Print FauFTBWay RTL. / 打印 FauFTBWay RTL。"""

    print(build_verilog(None, None))


if __name__ == "__main__":
    main()
