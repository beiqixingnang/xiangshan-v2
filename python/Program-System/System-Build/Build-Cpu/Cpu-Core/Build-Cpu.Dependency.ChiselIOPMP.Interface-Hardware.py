"""UHSC Kunminghu V2 ChiselIOPMP interface family aggregate.
昆明湖 V2 ChiselIOPMP 接口族聚合边界。

The boundary keeps the source APB register map, IOPMP entry attributes,
NAPOT range matching, RRID admission, and request/response fault hand-off in
one deterministic Amaranth module.  AXI diplomacy is represented by the
explicit transaction boundary; parent integration remains a separate closure.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Mapping, Sequence, cast

from amaranth import Array, Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog
from amaranth.hdl.ast import Value
from amaranth.lib.coding import PriorityEncoder


# =============================================================================
# Module Contract
# =============================================================================
__all__ = [
    'IOPMPConfig',
    'IOPMPEntry',
    'napot_range',
    'iopmp_reference_check',
    'UHSCIOPMPInterface',
    'IOPMPInterface',
    'build_verilog',
    'main',
]


# Keep the three ChiselIOPMP sources at this aggregate boundary. /
# 在此聚合边界保留三个 ChiselIOPMP 源文件路径。


# Cast Amaranth's generator controls to the context-manager protocol. /
# 将 Amaranth 生成器控制转换为上下文管理器协议。
def amaranth_if(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.If(condition))


# Cast an Amaranth else branch to the context-manager protocol. /
# 将 Amaranth else 分支转换为上下文管理器协议。
def amaranth_else(module: Module) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Else())


# Cast an Amaranth elif branch to the context-manager protocol. /
# 将 Amaranth elif 分支转换为上下文管理器协议。
def amaranth_elif(module: Module, condition: Any) -> AbstractContextManager[None]:
    return cast(AbstractContextManager[None], module.Elif(condition))


# Narrow dynamic Amaranth expressions at the DSL boundary. /
# 在 DSL 边界窄化动态 Amaranth 表达式。
def amaranth_value(expression: Any) -> Value:
    return cast(Value, expression)


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class IOPMPConfig:
    """V2 IOPMP geometry and bounded register-map configuration. / V2 IOPMP 几何与寄存器映射配置。"""

    address_bits: int = 48
    rrid_bits: int = 16
    rrid_num: int = 32
    entry_num: int = 512
    reg_addr_bits: int = 32
    reg_data_bits: int = 32
    axi_data_bits: int = 256
    response_depth: int = 1

    # Validate source-backed widths and table geometry. / 校验源代码对应的位宽与表几何。
    def __post_init__(self) -> None:
        if self.address_bits < 32 or self.address_bits > 64:
            raise ValueError("address_bits must be in [32, 64]")
        if self.rrid_bits < 1 or self.rrid_num < 1 or self.rrid_num > (1 << self.rrid_bits):
            raise ValueError("invalid RRID geometry")
        if self.entry_num < 1 or self.entry_num > 1024:
            raise ValueError("entry_num must be in [1, 1024]")
        if self.reg_addr_bits < 16 or self.reg_data_bits != 32 or self.axi_data_bits % 8:
            raise ValueError("V2 register/data geometry is not supported")
        if self.response_depth != 1:
            raise ValueError("the source checker exposes one response at a time")


@dataclass(frozen=True)
class IOPMPEntry:
    """One source-shaped entry-table record. / 一个源代码形状的 entryTable 记录。"""

    address: int = 0
    permissions: int = 0
    mode: int = 0
    rrid_value: int = 0
    rrid_mask: int = 0


# =============================================================================
# Implementation
# =============================================================================
# Decode a NAPOT/NA4 encoded entry into an inclusive byte range. / 将 NAPOT/NA4 编码条目解码为闭区间字节地址范围。
def napot_range(address: int, mode: int = 3, address_bits: int = 48) -> tuple[int, int]:
    """Return the source NAPOTDecoder range for one encoded entry. / 返回单个编码条目的源 NAPOTDecoder 范围。"""

    if mode not in (2, 3):
        return (0, 0)
    width = address_bits + 2
    mask = (1 << width) - 1
    suffix = 1 if mode == 2 else 3
    encoded = ((int(address) << 2) | suffix) & mask
    napot_mask = encoded ^ ((encoded + 1) & mask)
    start = (encoded & ~napot_mask) >> 2
    end = (encoded | napot_mask) >> 2
    return start, end


# Check one request against the bounded IOPMP policy. / 按有界 IOPMP 策略检查单个请求。
def iopmp_reference_check(address: int, length: int, write: bool, rrid: int,
                          entries: Sequence[IOPMPEntry], enabled: bool = True,
                          rrid_num: int = 32, address_bits: int = 48) -> dict[str, int]:
    """Return match, read-fault, write-fault, and interrupt observations. / 返回匹配、读错、写错和中断观测值。"""

    if not enabled:
        return {"matched": 0, "read_fault": 0, "write_fault": 0, "interrupt": 0, "entry": 0}
    request_length = max(1, int(length))
    request_address = int(address) & ((1 << address_bits) - 1)
    request_sum = request_address + request_length
    # A wrapped request is never admitted: the source checker operates on a
    # fixed-width physical address and must not accidentally match address 0
    # after an arithmetic truncation.
    if request_sum > (1 << address_bits):
        return {"matched": 0, "read_fault": int(not write), "write_fault": int(write), "interrupt": 1, "entry": 0}
    request_end = request_sum - 1
    selected: IOPMPEntry | None = None
    selected_index = 0
    for index, entry in enumerate(entries):
        if entry.mode not in (2, 3) or rrid >= rrid_num:
            continue
        if entry.rrid_mask and (rrid & entry.rrid_mask) != (entry.rrid_value & entry.rrid_mask):
            continue
        start, end = napot_range(entry.address, entry.mode, address_bits)
        if request_address >= start and request_end <= end:
            selected = entry
            selected_index = index
            break
    if selected is None:
        return {"matched": 0, "read_fault": int(not write), "write_fault": int(write), "interrupt": 1, "entry": 0}
    read_fault = int(not write and not (selected.permissions & 0x1))
    write_fault = int(write and not (selected.permissions & 0x2))
    return {"matched": 1, "read_fault": read_fault, "write_fault": write_fault,
            "interrupt": int(read_fault or write_fault), "entry": selected_index}


class UHSCIOPMPInterface(Elaboratable):
    """APB-configurable IOPMP checker and transaction response boundary. / 可由 APB 配置的 IOPMP 检查器与事务响应边界。"""

    # Initialize source-shaped APB, transaction, and status ports. / 初始化源代码形状的 APB、事务和状态端口。
    def __init__(self, configuration: IOPMPConfig | None = None) -> None:
        self.config = configuration or IOPMPConfig()
        c = self.config
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.csr_valid = Signal(name="io_apb_valid")
        self.csr_write = Signal(name="io_apb_write")
        self.csr_addr = Signal(c.reg_addr_bits, name="io_apb_addr")
        self.csr_wdata = Signal(c.reg_data_bits, name="io_apb_wdata")
        self.csr_rdata = Signal(c.reg_data_bits, name="io_apb_rdata")
        self.csr_ready = Signal(name="io_apb_ready")
        self.req_valid = Signal(name="io_req_valid")
        self.req_ready = Signal(name="io_req_ready")
        self.req_write = Signal(name="io_req_write")
        self.req_rrid = Signal(c.rrid_bits, name="io_req_rrid")
        self.req_address = Signal(c.address_bits, name="io_req_address")
        self.req_length = Signal(c.address_bits, name="io_req_length")
        self.resp_valid = Signal(name="io_resp_valid")
        self.resp_ready = Signal(name="io_resp_ready")
        self.resp_read_fault = Signal(name="io_resp_read_fault")
        self.resp_write_fault = Signal(name="io_resp_write_fault")
        self.resp_entry = Signal(max(1, (c.entry_num + 1).bit_length()), name="io_resp_entry")
        self.interrupt = Signal(name="io_interrupt")
        self.flush = Signal(name="io_flush")
        self.enable = Signal(name="io_enable")

    # Elaborate APB register state, NAPOT matching, and one-entry response flow. / 展开 APB 寄存器状态、NAPOT 匹配和单项响应流程。
    def elaborate(self, platform: Any) -> Module:
        del platform
        c = self.config
        m = Module()
        domain = ClockDomain("iopmp", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.iopmp = domain

        enable_reg = Signal(reset=0, name="iopmp_enable_reg")
        err_interrupt = Signal(reset=0, name="iopmp_err_interrupt")
        errcfg = Signal(32, reset=0, name="iopmp_errcfg")
        errinfo = Signal(32, reset=0, name="iopmp_errinfo")
        err_addr = Signal(c.address_bits, reset=0, name="iopmp_err_addr")
        err_rrid = Signal(c.rrid_bits, reset=0, name="iopmp_err_rrid")
        response_valid = Signal(reset=0, name="iopmp_response_valid")
        response_read_fault = Signal(reset=0, name="iopmp_response_read_fault")
        response_write_fault = Signal(reset=0, name="iopmp_response_write_fault")
        response_entry = Signal(len(self.resp_entry), reset=0, name="iopmp_response_entry")
        entry_low = Array(Signal(32, reset=0, name=f"entry_addr_{i}_lo") for i in range(c.entry_num))
        entry_high = Array(Signal(max(1, c.address_bits - 32), reset=0, name=f"entry_addr_{i}_hi") for i in range(c.entry_num))
        entry_cfg = Array(Signal(11, reset=0, name=f"entry_cfg_{i}") for i in range(c.entry_num))
        # RRID attributes are kept separately from the source entry cfg word.
        # This preserves the 16-byte entry table while exposing a deterministic
        # extension window for the bounded aggregate (0x3000..0x3fff).
        entry_rrid_value = Array(Signal(c.rrid_bits, reset=0, name=f"entry_rrid_{i}_value")
                                 for i in range(c.entry_num))
        entry_rrid_mask = Array(Signal(c.rrid_bits, reset=0, name=f"entry_rrid_{i}_mask")
                                for i in range(c.entry_num))
        # Cat's first operand occupies the low bits, so place ENTRY_ADDR_LO
        # first and append ENTRY_ADDRH above it (matching the Scala
        # ``Cat(entry_addrh, entry_addr)`` convention).
        entry_addr = [Cat(entry_low[i], entry_high[i])[:c.address_bits] for i in range(c.entry_num)]

        # Decode APB register windows and dynamic entry-table addressing. / 解码 APB 寄存器窗口与动态 entryTable 地址。
        entry_window = (self.csr_addr >= 0x2000) & (self.csr_addr < (0x2000 + c.entry_num * 16))
        rrid_window = (self.csr_addr >= 0x3000) & (self.csr_addr < (0x3000 + c.entry_num * 8))
        entry_index = (self.csr_addr - 0x2000) >> 4
        rrid_index = (self.csr_addr - 0x3000) >> 3
        entry_word = self.csr_addr[2:4]
        rrid_word = self.csr_addr[2:3]
        m.d.comb += [self.csr_ready.eq(self.csr_valid), self.enable.eq(enable_reg), self.interrupt.eq(err_interrupt)]

        # Build a lowest-index priority match for the current request. / 为当前请求构造最低索引优先匹配。
        request_length = amaranth_value(Mux(self.req_length == 0, 1, self.req_length))
        # Cat places its first operand in the least-significant bits; append a
        # zero above each operand to form a true zero-extended sum.
        request_address_ext = amaranth_value(Cat(self.req_address, Const(0)))
        request_length_ext = amaranth_value(Cat(request_length, Const(0)))
        request_sum = amaranth_value(request_address_ext + request_length_ext)
        request_overflow = amaranth_value(request_sum[c.address_bits])
        request_end = amaranth_value(request_sum[:c.address_bits] - 1)
        match_bits: list[Any] = []
        for index in range(c.entry_num):
            mode = entry_cfg[index][3:5]
            valid_mode = (mode == 2) | (mode == 3)
            # The source stores address bits above the two-byte granularity
            # boundary.  Decode the NAPOT suffix before comparing byte
            # addresses, matching ``napot_range`` above.
            suffix = Mux(mode == 2, 1, 3)
            encoded_base = amaranth_value(Cat(Const(0, 2), entry_addr[index]))
            encoded = amaranth_value(encoded_base | suffix)
            napot_mask = amaranth_value(encoded ^ (encoded + 1))
            range_start = amaranth_value((encoded & ~napot_mask) >> 2)
            range_end = amaranth_value((encoded | napot_mask) >> 2)
            rrid_match = (self.req_rrid < c.rrid_num) & (
                (self.req_rrid & entry_rrid_mask[index]) ==
                (entry_rrid_value[index] & entry_rrid_mask[index]))
            full_match = valid_mode & rrid_match & ~request_overflow & (self.req_address >= range_start) & (request_end <= range_end)
            match_bits.append(full_match)
        match_vector = Cat(*match_bits)
        selected_index = Signal(len(self.resp_entry), name="iopmp_selected_entry")
        encoder = PriorityEncoder(c.entry_num)
        m.submodules.iopmp_priority_encoder = encoder
        m.d.comb += encoder.i.eq(match_vector)
        selected_read = amaranth_value(Array(entry_cfg[index][0] for index in range(c.entry_num))[selected_index])
        selected_write = amaranth_value(Array(entry_cfg[index][1] for index in range(c.entry_num))[selected_index])
        m.d.comb += selected_index.eq(encoder.o)
        matched = ~encoder.n
        no_rule = ~matched
        read_fault_now = enable_reg & (~self.req_write) & (no_rule | ~selected_read)
        write_fault_now = enable_reg & self.req_write & (no_rule | ~selected_write)
        request_fire = self.req_valid & self.req_ready
        response_fire = response_valid & self.resp_ready
        m.d.comb += [
            self.req_ready.eq(~response_valid),
            self.resp_read_fault.eq(response_read_fault), self.resp_write_fault.eq(response_write_fault),
            self.resp_entry.eq(response_entry), self.resp_valid.eq(response_valid),
            self.flush.eq(response_valid & (response_read_fault | response_write_fault)),
        ]

        # Expose source register values through the APB read path. / 通过 APB 读路径暴露源代码寄存器值。
        read_value = Const(0, 32)
        read_value = Mux(self.csr_addr[0:16] == 0x0008, Cat(Const(0, 31), enable_reg), read_value)
        read_value = Mux(self.csr_addr[0:16] == 0x000C, Const(c.rrid_num, 32), read_value)
        read_value = Mux(self.csr_addr[0:16] == 0x0010, Const(0, 32), read_value)
        read_value = Mux(self.csr_addr[0:16] == 0x0060, errcfg, read_value)
        read_value = Mux(self.csr_addr[0:16] == 0x0064, errinfo, read_value)
        entry_read = amaranth_value(Array(entry_low[i] for i in range(c.entry_num))[entry_index])
        entry_high_read = amaranth_value(Array(entry_high[i] for i in range(c.entry_num))[entry_index])
        entry_cfg_read = amaranth_value(Array(entry_cfg[i] for i in range(c.entry_num))[entry_index])
        rrid_value_read = amaranth_value(Array(entry_rrid_value[i] for i in range(c.entry_num))[rrid_index])
        rrid_mask_read = amaranth_value(Array(entry_rrid_mask[i] for i in range(c.entry_num))[rrid_index])
        entry_value = Mux(entry_word == 0, entry_read,
                          Mux(entry_word == 1, Cat(entry_high_read, Const(0, 32 - max(1, c.address_bits - 32))),
                              Cat(entry_cfg_read, Const(0, 21))))
        rrid_value_word = Cat(rrid_value_read, Const(0, 32 - c.rrid_bits)) if c.rrid_bits < 32 else rrid_value_read[:32]
        rrid_mask_word = Cat(rrid_mask_read, Const(0, 32 - c.rrid_bits)) if c.rrid_bits < 32 else rrid_mask_read[:32]
        m.d.comb += self.csr_rdata.eq(Mux(entry_window, entry_value,
                                           Mux(rrid_window, Mux(rrid_word == 0, rrid_value_word, rrid_mask_word), read_value)))

        # Update tables, capture first faults, and retire responses synchronously. / 同步更新表项、捕获首个错误并完成响应。
        with amaranth_if(m, self.reset):
            m.d.iopmp += [enable_reg.eq(0), err_interrupt.eq(0), errcfg.eq(0), errinfo.eq(0), err_addr.eq(0), err_rrid.eq(0),
                          response_valid.eq(0), response_read_fault.eq(0), response_write_fault.eq(0), response_entry.eq(0)]
        with amaranth_else(m):
            with amaranth_if(m, self.csr_valid & self.csr_write):
                with amaranth_if(m, self.csr_addr[0:16] == 0x0008):
                    m.d.iopmp += enable_reg.eq(self.csr_wdata[0])
                with amaranth_if(m, self.csr_addr[0:16] == 0x0060):
                    m.d.iopmp += errcfg.eq(self.csr_wdata)
                with amaranth_if(m, amaranth_value(self.csr_addr[0:16] == 0x0064) & amaranth_value(self.csr_wdata[31])):
                    errinfo.eq(0)
                    err_interrupt.eq(0)
                with amaranth_if(m, entry_window & (entry_index < c.entry_num)):
                    with amaranth_if(m, entry_word == 0):
                        m.d.iopmp += entry_low[entry_index].eq(self.csr_wdata)
                    with amaranth_elif(m, entry_word == 1):
                        m.d.iopmp += entry_high[entry_index].eq(self.csr_wdata[:max(1, c.address_bits - 32)])
                    with amaranth_elif(m, entry_word == 2):
                        m.d.iopmp += entry_cfg[entry_index].eq(self.csr_wdata[:11])
            with amaranth_if(m, self.csr_valid & self.csr_write & rrid_window & (rrid_index < c.entry_num)):
                with amaranth_if(m, rrid_word == 0):
                    m.d.iopmp += entry_rrid_value[rrid_index].eq(self.csr_wdata[:c.rrid_bits])
                with amaranth_elif(m, rrid_word == 1):
                    m.d.iopmp += entry_rrid_mask[rrid_index].eq(self.csr_wdata[:c.rrid_bits])
            with amaranth_if(m, request_fire):
                m.d.iopmp += [
                    response_valid.eq(1), response_read_fault.eq(read_fault_now),
                    response_write_fault.eq(write_fault_now), response_entry.eq(selected_index),
                    errinfo.eq(Cat(Const(0, 15), selected_index, Const(0, 14), write_fault_now, read_fault_now, 1)),
                    err_addr.eq(self.req_address), err_rrid.eq(self.req_rrid),
                ]
                with amaranth_if(m, read_fault_now | write_fault_now):
                    m.d.iopmp += err_interrupt.eq(1)
            with amaranth_if(m, response_fire):
                m.d.iopmp += response_valid.eq(0)
        return m


IOPMPInterface = UHSCIOPMPInterface


# =============================================================================
# Public Adapter
# =============================================================================
# Export deterministic Verilog for the IOPMP family boundary. / 为 IOPMP 族边界导出确定性 Verilog。
def build_verilog(configuration: IOPMPConfig | Mapping[str, Any] | None,
                  injected_dependencies: Mapping[str, Any]) -> str:
    """Return Verilog for the configured aggregate. / 返回配置聚合的 Verilog。"""

    del injected_dependencies
    if configuration is None:
        cfg, name = IOPMPConfig(), "UHSCIOPMPInterface"
    elif isinstance(configuration, IOPMPConfig):
        cfg, name = configuration, "UHSCIOPMPInterface"
    else:
        fields = IOPMPConfig.__dataclass_fields__
        cfg = IOPMPConfig(**{key: value for key, value in dict(configuration).items() if key in fields})
        name = str(configuration.get("module", "UHSCIOPMPInterface"))
    top = UHSCIOPMPInterface(cfg)
    ports = [top.clock, top.reset, top.csr_valid, top.csr_write, top.csr_addr, top.csr_wdata,
             top.csr_rdata, top.csr_ready, top.req_valid, top.req_ready, top.req_write,
             top.req_rrid, top.req_address, top.req_length, top.resp_valid, top.resp_ready,
             top.resp_read_fault, top.resp_write_fault, top.resp_entry, top.interrupt, top.flush, top.enable]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print a deterministic default export when invoked directly. / 直接调用时打印确定性的默认导出。
def main() -> None:
    """Print the default IOPMP Verilog. / 打印默认 IOPMP Verilog。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
