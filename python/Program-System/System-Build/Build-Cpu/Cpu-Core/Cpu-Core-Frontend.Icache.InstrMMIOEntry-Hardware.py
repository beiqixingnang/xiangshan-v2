"""V2 instruction-MMIO miss entry with its four-state handshake.
香山 V2 指令 MMIO 未缓存请求的四状态握手机。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# The V2 instruction MMIO entry is a single outstanding transaction engine.
# Its selected deployment removes unused metadata and ready signals, leaving
# the finite request, refill, response, and WFI boundary declared below.
# V2 指令 MMIO 表项只允许一个未完成事务；部署特化删除未使用元数据和 ready
# 信号，下面保留有限的请求、填充、响应与 WFI 边界。
__all__ = ["InstrMMIOEntryConfig", "InstrMMIOEntry", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class InstrMMIOEntryConfig:
    """Widths for the V2 MMIO entry. / V2 MMIO 表项的位宽配置。"""

    paddr_bits: int = 48
    mmio_bus_width: int = 64
    max_instr_len: int = 32
    mmio_bus_bytes: int = 8

    # Validate the finite V2 geometry. / 校验有限的 V2 几何参数。
    def __post_init__(self) -> None:
        if self.paddr_bits != 48:
            raise ValueError("the V2 MMIO entry uses 48-bit physical addresses")
        if self.mmio_bus_width != 64:
            raise ValueError("the V2 entry uses a 64-bit MMIO bus")
        if self.max_instr_len != 32:
            raise ValueError("the V2 entry returns 32-bit instructions")
        if self.mmio_bus_bytes != self.mmio_bus_width // 8:
            raise ValueError("mmio_bus_bytes must match mmio_bus_width")


# =============================================================================
# Implementation
# =============================================================================
class InstrMMIOEntry(Elaboratable):
    """One V2 uncached instruction transaction. / 一个 V2 未缓存指令事务。"""

    INVALID = 0
    REFILL_REQ = 1
    REFILL_RESP = 2
    SEND_RESP = 3

    # Construct the finite request, refill, response, and WFI ports.
    # 构造有限的请求、填充、响应与 WFI 端口。
    def __init__(self, configuration: InstrMMIOEntryConfig | None = None) -> None:
        self.configuration = configuration or InstrMMIOEntryConfig()
        cfg = self.configuration

        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")

        self.req_ready = Signal(name="io_req_ready")
        self.req_valid = Signal(name="io_req_valid")
        self.req_addr = Signal(cfg.paddr_bits, name="io_req_bits_addr")
        self.req_flush = Signal(name="io_req_bits_flush")

        self.resp_valid = Signal(name="io_resp_valid")
        self.resp_data = Signal(cfg.max_instr_len, name="io_resp_bits_data")
        self.resp_corrupt = Signal(name="io_resp_bits_corrupt")

        self.mmio_acquire_ready = Signal(name="io_mmio_acquire_ready")
        self.mmio_acquire_valid = Signal(name="io_mmio_acquire_valid")
        self.mmio_acquire_address = Signal(cfg.paddr_bits,
                                           name="io_mmio_acquire_bits_address")
        self.mmio_grant_valid = Signal(name="io_mmio_grant_valid")
        self.mmio_grant_data = Signal(cfg.mmio_bus_width,
                                      name="io_mmio_grant_bits_data")
        self.mmio_grant_corrupt = Signal(name="io_mmio_grant_bits_corrupt")

        self.wfi_req = Signal(name="io_wfi_wfiReq")
        self.wfi_safe = Signal(name="io_wfi_wfiSafe")

    # Elaborate the four-state request/refill/response machine. / 展开请求、填充和响应四态机。
    def elaborate(self, platform: Any) -> Module:
        del platform
        cfg = self.configuration
        # The Amaranth DSL context manager is generated dynamically.
        module: Any = Module()

        # Use an active-high asynchronous reset for the state-bearing signals.
        # 为状态信号使用高有效异步复位。
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        module.domains.sync = domain

        state = Signal(2, reset=self.INVALID, name="state")
        # Keep the request address resetless while clearing response metadata.
        # 请求地址保持无复位，响应元数据在复位时清零。
        req_addr_reg = Signal(cfg.paddr_bits, name="req_addr", reset_less=True)
        resp_data_reg = Signal(cfg.mmio_bus_width, reset=0, name="respDataReg")
        resp_corrupt_reg = Signal(reset=0, name="respCorruptReg")
        need_flush = Signal(reset=0, name="needFlush")

        # Decode the four state values as one-bit equations.  Keeping the
        # reductions explicit avoids treating a two-bit vector as a Boolean.
        # 将四个状态值展开为单比特方程，避免把两位向量直接当布尔值。
        state_bit_0 = cast(Any, state[0])
        state_bit_1 = cast(Any, state[1])
        state_invalid = ~(state_bit_0 | state_bit_1)
        state_refill_req = state_bit_0 & ~state_bit_1
        state_refill_resp = ~state_bit_0 & state_bit_1
        state_send_resp = state_bit_0 & state_bit_1

        req_fire = self.req_valid & state_invalid
        acquire_valid = state_refill_req & ~self.wfi_req
        acquire_fire = acquire_valid & self.mmio_acquire_ready
        grant_fire = state_refill_resp & self.mmio_grant_valid
        # The selected one-entry response arbiter accepts every response, so
        # grant_fire is qualified by valid alone.
        # 单项响应仲裁器始终接受响应，因此 grant_fire 只由 valid 门控。
        response_done = state_send_resp

        module.d.comb += [
            self.req_ready.eq(state_invalid),
            self.mmio_acquire_valid.eq(acquire_valid),
            self.mmio_acquire_address.eq(
                Cat(Const(0, 3), req_addr_reg[3:])
            ),
            self.resp_valid.eq(state_send_resp & ~need_flush),
            self.resp_corrupt.eq(resp_corrupt_reg),
            self.wfi_safe.eq(~state_refill_resp),
        ]

        # Select the instruction lane from the aligned 64-bit refill word.
        # 从对齐的 64 位填充字中选择指令所在的字道。
        addr_bit_1 = cast(Any, req_addr_reg[1])
        addr_bit_2 = cast(Any, req_addr_reg[2])
        lane_0 = ~addr_bit_1 & ~addr_bit_2
        lane_1 = addr_bit_1 & ~addr_bit_2
        lane_2 = ~addr_bit_1 & addr_bit_2
        lane_3 = addr_bit_1 & addr_bit_2
        lane_3_data = cast(Any, Cat(resp_data_reg[48:64], Const(0, 16)))
        module.d.comb += self.resp_data.eq(
            Mux(lane_0, resp_data_reg[0:32],
                Mux(lane_1, resp_data_reg[16:48],
                    Mux(lane_2, resp_data_reg[32:64],
                        Mux(lane_3, lane_3_data, Const(0, cfg.max_instr_len)))))
        )

        # Update needFlush with the ordered request and response conditions.
        # 按请求与响应条件的既定顺序更新 needFlush。
        module.d.sync += [
            need_flush.eq(
                (self.req_flush & ~state_invalid & ~state_send_resp)
                | (need_flush & ~state_send_resp)
            )
        ]

        # Prioritize response completion, grant, acquire, then allocation.
        # 按响应完成、grant、发起、分配的优先级更新状态。
        with module.If(response_done):
            module.d.sync += state.eq(self.INVALID)
        with module.Elif(state_refill_resp & self.mmio_grant_valid):
            module.d.sync += state.eq(self.SEND_RESP)
        with module.Elif(acquire_fire):
            module.d.sync += state.eq(self.REFILL_RESP)
        with module.Elif(req_fire):
            module.d.sync += state.eq(self.REFILL_REQ)

        # Capture request and grant payloads on their respective fires.
        # 在相应握手时锁存请求地址和 grant 数据。
        with module.If(req_fire):
            module.d.sync += req_addr_reg.eq(self.req_addr)
        with module.If(grant_fire):
            module.d.sync += [
                resp_data_reg.eq(self.mmio_grant_data),
                resp_corrupt_reg.eq(self.mmio_grant_corrupt),
            ]

        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Export deterministic Verilog for the finite deployment boundary.
# 为有限部署边界导出确定性的 Verilog。
def build_verilog(configuration, injected_dependencies):
    """Return the standalone InstrMMIOEntry Verilog. / 返回独立 InstrMMIOEntry Verilog。"""
    del injected_dependencies
    if isinstance(configuration, InstrMMIOEntryConfig):
        cfg = configuration
    elif isinstance(configuration, dict):
        fields = {"paddr_bits", "mmio_bus_width", "max_instr_len", "mmio_bus_bytes"}
        cfg = InstrMMIOEntryConfig(**{key: value for key, value in configuration.items()
                                      if key in fields})
    else:
        cfg = InstrMMIOEntryConfig()
    top = InstrMMIOEntry(cfg)
    ports = [
        top.clock, top.reset,
        top.req_ready, top.req_valid, top.req_addr, top.req_flush,
        top.resp_valid, top.resp_data, top.resp_corrupt,
        top.mmio_acquire_ready, top.mmio_acquire_valid,
        top.mmio_acquire_address, top.mmio_grant_valid,
        top.mmio_grant_data, top.mmio_grant_corrupt,
        top.wfi_req, top.wfi_safe,
    ]
    return verilog.convert(top, name="InstrMMIOEntry", ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the deterministic export for manual inspection. / 打印确定性导出供人工检查。
def main() -> None:
    """Print generated Verilog. / 打印生成的 Verilog。"""
    print(build_verilog(None, None))


if __name__ == "__main__":
    main()
