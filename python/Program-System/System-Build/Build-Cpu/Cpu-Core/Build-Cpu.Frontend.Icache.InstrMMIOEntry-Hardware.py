"""V2 instruction-MMIO miss entry with its four-state handshake.
香山 V2 指令 MMIO 未缓存请求的四状态握手机。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# InstrUncache.scala's InstrMMIOEntry is the single-entry transaction engine
# used by the selected V2 top.  The locked XSTop specialization prunes the
# source-id, memory-type, response-ready, and grant-ready fields: those are
# driven by constants or the one-entry arbiter.  The public boundary below is
# therefore the exact ten-signal observable specialization in XSTop.sv.
# InstrUncache.scala 中的 InstrMMIOEntry 是 V2 顶层实际使用的单项事务引擎。
# 锁定 XSTop 特化会删除由常量或单项仲裁器驱动的字段，因此保留其十个可观察端口。
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
        if self.paddr_bits < 4:
            raise ValueError("paddr_bits must be at least four")
        if self.mmio_bus_width != 64:
            raise ValueError("the locked V2 entry uses a 64-bit MMIO bus")
        if self.max_instr_len != 32:
            raise ValueError("the locked V2 entry returns 32-bit instructions")
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

    # Construct the locked XSTop observable ports. / 构造锁定 XSTop 可观察端口。
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

        # Match Chisel RegInit's active-high asynchronous reset topology.
        # 对齐 Chisel RegInit 的高有效异步复位拓扑。
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        module.domains.sync = domain

        state = Signal(2, reset=self.INVALID, name="state")
        # ``req_addr`` is a resetless Reg() in the locked reference; every other
        # register here is a RegInit(0) inside the reset-bearing block.
        # req_addr 在锁定参考中是无复位 Reg()，其余寄存器为 RegInit(0)。
        req_addr_reg = Signal(cfg.paddr_bits, name="req_addr", reset_less=True)
        resp_data_reg = Signal(cfg.mmio_bus_width, reset=0, name="respDataReg")
        resp_corrupt_reg = Signal(reset=0, name="respCorruptReg")
        need_flush = Signal(reset=0, name="needFlush")

        state_invalid = state == self.INVALID
        state_refill_req = state == self.REFILL_REQ
        state_refill_resp = state == self.REFILL_RESP
        state_send_resp = state == self.SEND_RESP

        req_fire = self.req_valid & state_invalid
        acquire_valid = state_refill_req & ~self.wfi_req
        acquire_fire = acquire_valid & self.mmio_acquire_ready
        grant_fire = state_refill_resp & self.mmio_grant_valid
        # The one-entry parent arbiter has ready permanently high in XSTop.
        # XSTop 中单项父仲裁器的 ready 永久为高，因此 grant_fire 只需 valid。
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

        # Select the instruction lane exactly as getDataFromBus in Scala.
        # 按 Scala 的 getDataFromBus 精确选择指令所在的总线字节道。
        module.d.comb += self.resp_data.eq(
            Mux(req_addr_reg[1:3] == 0, resp_data_reg[0:32],
                Mux(req_addr_reg[1:3] == 1, resp_data_reg[16:48],
                    Mux(req_addr_reg[1:3] == 2, resp_data_reg[32:64],
                        Cat(resp_data_reg[48:64], Const(0, 16)))))
        )

        # Update needFlush with the source's ordered when/elsewhen equation.
        # 按源代码 when/elsewhen 顺序更新 needFlush。
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
# Export deterministic Verilog for the exact XSTop specialization.
# 为锁定 XSTop 特化导出确定性的 Verilog。
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
