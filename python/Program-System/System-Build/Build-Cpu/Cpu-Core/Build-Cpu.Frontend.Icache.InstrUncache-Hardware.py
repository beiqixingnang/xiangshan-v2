"""UHSC Kunminghu V2 instruction uncache parent.
昆明湖 V2 指令非缓存父级，聚合单项 MMIO 事务并桥接 TileLink。

The locked V2 specialization contains one ``InstrMMIOEntry``.  This
single-file implementation keeps that hierarchy explicit and exposes the
same observable client/request/response surface as XSTop.sv.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# InstrUncache.scala allocates one entry in Kunminghu V2 (nMMIOs == 1),
# arbitrates its response, and forwards one TileLink A/D channel.  The
# generated XSTop module therefore has no source-id or ready output ports.
# InstrUncache.scala 在昆明湖 V2 中分配一个事务项（nMMIOs == 1），仲裁响应并
# 转发单路 TileLink A/D；因此锁定 XSTop 不暴露 source-id 或 ready 输出。

__all__ = [
    "COVERED_MODULES", "InstrUncacheConfig", "InstrUncache", "build_verilog", "main",
]

COVERED_MODULES: tuple[str, ...] = ("InstrUncache",)


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class InstrUncacheConfig:
    """Finite locked V2 widths. / 锁定 V2 的有限位宽。"""

    paddr_bits: int = 48
    mmio_bus_width: int = 64
    instr_bits: int = 32
    mmio_bus_bytes: int = 8

    # Keep parameters aligned with the locked specialization. / 与锁定特化保持一致。
    def __post_init__(self) -> None:
        if self.paddr_bits != 48:
            raise ValueError("Kunminghu V2 InstrUncache uses 48-bit physical addresses")
        if self.mmio_bus_width != 64 or self.instr_bits != 32:
            raise ValueError("locked InstrUncache uses a 64-bit bus and 32-bit instructions")
        if self.mmio_bus_bytes != self.mmio_bus_width // 8:
            raise ValueError("mmio_bus_bytes must match mmio_bus_width")


# =============================================================================
# Implementation
# =============================================================================
class InstrUncache(Elaboratable):
    """One-entry InstrUncache parent matching locked XSTop equations.
    与锁定 XSTop 方程一致的单项 InstrUncache 父级。
    """

    INVALID = 0
    REFILL_REQ = 1
    REFILL_RESP = 2
    SEND_RESP = 3

    # Construct the generated XSTop observable ports. / 构造 XSTop 可观察端口。
    def __init__(self, configuration: InstrUncacheConfig | None = None) -> None:
        self.configuration = configuration or InstrUncacheConfig()
        cfg = self.configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")

        self.client_out_a_ready = Signal(name="auto_client_out_a_ready")
        self.client_out_a_valid = Signal(name="auto_client_out_a_valid")
        self.client_out_a_bits_address = Signal(cfg.paddr_bits, name="auto_client_out_a_bits_address")
        self.client_out_d_valid = Signal(name="auto_client_out_d_valid")
        self.client_out_d_bits_source = Signal(name="auto_client_out_d_bits_source")
        self.client_out_d_bits_data = Signal(cfg.mmio_bus_width, name="auto_client_out_d_bits_data")
        self.client_out_d_bits_corrupt = Signal(name="auto_client_out_d_bits_corrupt")

        self.req_ready = Signal(name="io_req_ready")
        self.req_valid = Signal(name="io_req_valid")
        self.req_addr = Signal(cfg.paddr_bits, name="io_req_bits_addr")
        self.req_flush = Signal(name="io_req_bits_flush")
        self.resp_valid = Signal(name="io_resp_valid")
        self.resp_data = Signal(cfg.instr_bits, name="io_resp_bits_data")
        self.resp_error = Signal(name="io_resp_bits_corrupt")
        self.wfi_req = Signal(name="io_wfi_wfiReq")
        self.wfi_safe = Signal(name="io_wfi_wfiSafe")

        # Compact aliases consumed by FrontendParent. / FrontendParent 使用的紧凑别名。
        self.mmio_acquire_ready = self.client_out_a_ready
        self.mmio_acquire_valid = self.client_out_a_valid
        self.mmio_acquire_address = self.client_out_a_bits_address
        self.mmio_grant_valid = self.client_out_d_valid & ~self.client_out_d_bits_source
        self.mmio_grant_source = self.client_out_d_bits_source
        self.mmio_grant_data = self.client_out_d_bits_data
        self.mmio_grant_corrupt = self.client_out_d_bits_corrupt

    # Emit the one-entry request/refill/response state machine. / 展开单项状态机。
    def elaborate(self, platform: Any) -> Module:
        del platform
        cfg = self.configuration
        # The Amaranth DSL context manager is generated dynamically.
        module: Any = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        module.domains.sync = domain

        # Preserve the locked child-instance state names so the parent proof can
        # pair the exact InstrMMIOEntry registers after flattening.  req_addr is
        # a resetless Reg() in Scala; the remaining four are RegInit values.
        # 保留锁定子实例状态名；req_addr 为无复位 Reg()，其余四项为 RegInit。
        state = Signal(2, reset=self.INVALID, name="entries_0.state")
        req_addr_reg = Signal(
            cfg.paddr_bits, reset_less=True, name="entries_0.req_addr"
        )
        resp_data_reg = Signal(
            cfg.mmio_bus_width, reset=0, name="entries_0.respDataReg"
        )
        resp_corrupt_reg = Signal(reset=0, name="entries_0.respCorruptReg")
        need_flush = Signal(reset=0, name="entries_0.needFlush")
        # Decode the four states bitwise to keep generated comparisons
        # explicitly one-bit and warning-free under Verilator.
        state_0 = cast(Any, state[0])
        state_1 = cast(Any, state[1])
        invalid = ~(state_0 | state_1)
        refill_req = state_0 & ~state_1
        refill_resp = ~state_0 & state_1
        send_resp = state_0 & state_1

        req_fire = self.req_valid & invalid
        acquire_valid = refill_req & ~self.wfi_req
        acquire_fire = acquire_valid & self.client_out_a_ready
        grant_fire = refill_resp & self.client_out_d_valid & ~self.client_out_d_bits_source

        response_word = Signal(cfg.instr_bits, name="response_word")
        module.d.comb += response_word.eq(resp_data_reg[:32])
        req_addr_bit_1 = cast(Any, req_addr_reg[1])
        req_addr_bit_2 = cast(Any, req_addr_reg[2])
        with module.If(req_addr_bit_1 & ~req_addr_bit_2):
            module.d.comb += response_word.eq(resp_data_reg[16:48])
        with module.Elif(~req_addr_bit_1 & req_addr_bit_2):
            module.d.comb += response_word.eq(resp_data_reg[32:64])
        with module.Elif(req_addr_bit_1 & req_addr_bit_2):
            module.d.comb += response_word.eq(cast(Any, Cat(resp_data_reg[48:64], Const(0, 16))))
        module.d.comb += [
            self.req_ready.eq(invalid),
            self.client_out_a_valid.eq(acquire_valid),
            self.client_out_a_bits_address.eq(Cat(Const(0, 3), req_addr_reg[3:])),
            self.resp_valid.eq(send_resp & ~need_flush),
            self.resp_data.eq(response_word),
            self.resp_error.eq(resp_corrupt_reg),
            self.wfi_safe.eq(~refill_resp),
        ]
        # Locked arbiter always accepts a response; state clears on send cycle.
        module.d.sync += need_flush.eq(
            (self.req_flush & ~invalid & ~send_resp) | (need_flush & ~send_resp))
        with module.If(send_resp):
            module.d.sync += state.eq(self.INVALID)
        with module.Elif(grant_fire):
            module.d.sync += state.eq(self.SEND_RESP)
        with module.Elif(acquire_fire):
            module.d.sync += state.eq(self.REFILL_RESP)
        with module.Elif(req_fire):
            module.d.sync += state.eq(self.REFILL_REQ)
        with module.If(req_fire):
            module.d.sync += req_addr_reg.eq(self.req_addr)
        with module.If(grant_fire):
            module.d.sync += [resp_data_reg.eq(self.client_out_d_bits_data),
                              resp_corrupt_reg.eq(self.client_out_d_bits_corrupt)]
        return module


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration, injected_dependencies):
    """Return deterministic Verilog for the locked InstrUncache surface.
    返回锁定 InstrUncache 接口的确定性 Verilog。
    """
    del injected_dependencies
    cfg = configuration if isinstance(configuration, InstrUncacheConfig) else InstrUncacheConfig()
    top = InstrUncache(cfg)
    ports = [top.clock, top.reset, top.client_out_a_ready, top.client_out_a_valid,
             top.client_out_a_bits_address, top.client_out_d_valid,
             top.client_out_d_bits_source, top.client_out_d_bits_data,
             top.client_out_d_bits_corrupt, top.req_ready, top.req_valid,
             top.req_addr, top.req_flush, top.resp_valid, top.resp_data,
             top.resp_error, top.wfi_req, top.wfi_safe]
    return verilog.convert(top, name="InstrUncache", ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print deterministic Verilog. / 打印确定性 Verilog。"""
    print(build_verilog(None, None))


if __name__ == "__main__":
    main()
