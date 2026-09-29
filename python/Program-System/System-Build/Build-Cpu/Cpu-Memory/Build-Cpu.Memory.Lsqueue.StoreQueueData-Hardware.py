"""UHSC V2 store-queue address and data families.
昆明湖 V2 存储队列地址与数据 family。
"""

from __future__ import annotations

from typing import Any, cast

from amaranth import Array, Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
PortSpec = tuple[str, str, int]

__all__ = ["COVERED_MODULES", "PORT_SPECS", "StoreQueueDataFamily", "build_verilog", "main"]

COVERED_MODULES: tuple[str, ...] = (
    "SQAddrModule", "SQAddrModule_1", "SQData8Module", "SQDataModule",
)


# =============================================================================
# Configuration
# =============================================================================
ENTRY_COUNT = 56
ADDRESS_WIDTH = 6
BANK_COUNT = 8
BANK_SELECT_WIDTH = 3
BANK_DEPTH = 7
BYTE_COUNT = 16


# Construct one address-array port surface. / 构造一个地址阵列端口表面。
def addr_specs(data_width: int, include_read_lineflag: bool) -> tuple[PortSpec, ...]:
    """Return the ordered address-array ABI. / 返回有序地址阵列 ABI。"""

    ports: list[PortSpec] = [("clock", "input", 1), ("reset", "input", 1)]
    ports.extend((f"io_raddr_{index}", "input", ADDRESS_WIDTH) for index in range(2))
    ports.extend((f"io_rdata_{index}", "output", data_width) for index in range(2))
    if include_read_lineflag:
        ports.extend((f"io_rlineflag_{index}", "output", 1) for index in range(2))
    ports.extend((f"io_wen_{index}", "input", 1) for index in range(2))
    ports.extend((f"io_waddr_{index}", "input", ADDRESS_WIDTH) for index in range(2))
    ports.extend((f"io_wdata_{index}", "input", data_width) for index in range(2))
    ports.extend((f"io_wmask_{index}", "input", BYTE_COUNT) for index in range(2))
    ports.extend((f"io_wlineflag_{index}", "input", 1) for index in range(2))
    ports.extend((f"io_forwardMdata_{index}", "input", data_width) for index in range(3))
    ports.extend((f"io_forwardDataMask_{index}", "input", BYTE_COUNT) for index in range(3))
    ports.extend(
        (f"io_forwardMmask_{forward}_{entry}", "output", 1)
        for forward in range(3)
        for entry in range(ENTRY_COUNT)
    )
    return tuple(ports)


# Construct the byte-array port surface. / 构造字节阵列端口表面。
def data8_specs() -> tuple[PortSpec, ...]:
    """Return the ordered byte data-array ABI. / 返回有序字节数据阵列 ABI。"""

    ports: list[PortSpec] = [("clock", "input", 1), ("reset", "input", 1)]
    ports.extend((f"io_raddr_{index}", "input", ADDRESS_WIDTH) for index in range(2))
    for index in range(2):
        ports.extend(((f"io_rdata_{index}_valid", "output", 1), (f"io_rdata_{index}_data", "output", 8)))
    ports.extend((f"io_data_wen_{index}", "input", 1) for index in range(2))
    ports.extend((f"io_data_waddr_{index}", "input", ADDRESS_WIDTH) for index in range(2))
    ports.extend((f"io_data_wdata_{index}", "input", 8) for index in range(2))
    ports.extend((f"io_mask_wen_{index}", "input", 1) for index in range(2))
    ports.extend((f"io_mask_waddr_{index}", "input", ADDRESS_WIDTH) for index in range(2))
    ports.extend((f"io_mask_wdata_{index}", "input", 1) for index in range(2))
    ports.extend(
        (f"io_needForward_{forward}_{half}", "input", ENTRY_COUNT)
        for forward in range(3)
        for half in range(2)
    )
    ports.extend((f"io_forwardValid_{forward}", "output", 1) for forward in range(3))
    ports.extend((f"io_forwardData_{forward}", "output", 8) for forward in range(3))
    return tuple(ports)


# Construct the wide data-array port surface. / 构造宽数据阵列端口表面。
def data_specs() -> tuple[PortSpec, ...]:
    """Return the ordered 128-bit data-array ABI. / 返回有序 128 位数据阵列 ABI。"""

    ports: list[PortSpec] = [("clock", "input", 1), ("reset", "input", 1)]
    ports.extend((f"io_raddr_{index}", "input", ADDRESS_WIDTH) for index in range(2))
    for index in range(2):
        ports.extend(((f"io_rdata_{index}_mask", "output", BYTE_COUNT),
                      (f"io_rdata_{index}_data", "output", BYTE_COUNT * 8)))
    ports.extend((f"io_data_wen_{index}", "input", 1) for index in range(2))
    ports.extend((f"io_data_waddr_{index}", "input", ADDRESS_WIDTH) for index in range(2))
    ports.extend((f"io_data_wdata_{index}", "input", BYTE_COUNT * 8) for index in range(2))
    ports.extend((f"io_mask_wen_{index}", "input", 1) for index in range(2))
    ports.extend((f"io_mask_waddr_{index}", "input", ADDRESS_WIDTH) for index in range(2))
    ports.extend((f"io_mask_wdata_{index}", "input", BYTE_COUNT) for index in range(2))
    ports.extend(
        (f"io_needForward_{forward}_{half}", "input", ENTRY_COUNT)
        for forward in range(3)
        for half in range(2)
    )
    ports.extend(
        (f"io_forwardMask_{forward}_{byte}", "output", 1)
        for forward in range(3)
        for byte in range(BYTE_COUNT)
    )
    ports.extend(
        (f"io_forwardData_{forward}_{byte}", "output", 8)
        for forward in range(3)
        for byte in range(BYTE_COUNT)
    )
    return tuple(ports)


PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    "SQAddrModule": addr_specs(48, True),
    "SQAddrModule_1": addr_specs(50, False),
    "SQData8Module": data8_specs(),
    "SQDataModule": data_specs(),
}


# =============================================================================
# Implementation
# =============================================================================
class StoreQueueDataFamily(Elaboratable):
    """One selected store-queue data specialization. / 一个选定的存储队列数据特化。"""

    # Declare the selected public ports. / 声明选定的公开端口。
    def __init__(self, member: str = "SQAddrModule") -> None:
        """Create one selected specialization. / 创建一个选定特化。"""

        if member not in PORT_SPECS:
            raise ValueError(f"unsupported store-queue member: {member}")
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports: dict[str, Signal] = {
            name: Signal(width, name=name) for name, _direction, width in self.specs
        }
        self.clock = self.ports["clock"]
        self.reset = self.ports["reset"]

    # Select an entry with the defined out-of-range fallback. / 按定义的越界回退选择条目。
    def read_entry(self, entries: Array, address: Any) -> Any:
        """Return a registered-address lookup. / 返回寄存器地址查找。"""

        # Keep the lookup as an ArrayProxy so the simulator does not have to
        # compile a 56-level Python ``Mux`` expression.  Chisel Vec indexing
        # uses entry zero as its default for the six-bit addresses above the
        # 56-entry store queue, so preserve that locked behavior explicitly.
        return Mux(address < ENTRY_COUNT, entries[address], entries[0])

    # Add one delayed, bank-routed write path. / 添加一个延迟的分 bank 写路径。
    def add_banked_write_pipeline(
        self,
        module: Module,
        entries: Array,
        port_prefix: str,
        state_prefix: str | None,
        state_write_offset: int,
        width: int,
    ) -> None:
        """Implement the two-write one-cycle bank pipeline. / 实现双写一周期 bank 流水。"""

        stages: list[list[tuple[Signal, Signal, Signal]]] = []
        for write in range(2):
            by_bank: list[tuple[Signal, Signal, Signal]] = []
            for bank in range(BANK_COUNT):
                if state_prefix is None:
                    enabled = Signal(name=f"{port_prefix}_s1_enable_{write}_{bank}")
                    index = Signal(
                        BANK_SELECT_WIDTH,
                        name=f"{port_prefix}_s1_index_{write}_{bank}",
                        reset_less=True,
                    )
                    payload = Signal(
                        width,
                        name=f"{port_prefix}_s1_payload_{write}_{bank}",
                        reset_less=True,
                    )
                else:
                    state_write = write + state_write_offset
                    enabled = Signal(name=f"s1_wenVec_r_{state_write}_{bank}")
                    index = Signal(
                        BANK_SELECT_WIDTH,
                        name=f"{state_prefix}_s1_waddr_{write}_bank_{bank}",
                        reset_less=True,
                    )
                    payload = Signal(
                        width,
                        name=f"{state_prefix}_s1_wdata_{write}_bank_{bank}",
                        reset_less=True,
                    )
                by_bank.append((enabled, index, payload))
            stages.append(by_bank)

        for bank in range(BANK_COUNT):
            low_enable, low_index, low_payload = stages[0][bank]
            high_enable, high_index, high_payload = stages[1][bank]
            for index in range(BANK_DEPTH):
                entry = index * BANK_COUNT + bank
                with cast(Any, module.If(high_enable & (high_index == index))):
                    module.d.sync += entries[entry].eq(high_payload)
                with cast(Any, module.Elif(low_enable & (low_index == index))):
                    module.d.sync += entries[entry].eq(low_payload)

        for write in range(2):
            address = self.ports[f"{port_prefix}_waddr_{write}"]
            payload = self.ports[f"{port_prefix}_wdata_{write}"]
            enabled = self.ports[f"{port_prefix}_wen_{write}"]
            for bank in range(BANK_COUNT):
                stage_enable, stage_index, stage_payload = stages[write][bank]
                route = enabled & (address[:BANK_SELECT_WIDTH] == bank)
                module.d.sync += stage_enable.eq(route)
                with cast(Any, module.If(route)):
                    module.d.sync += [
                        stage_index.eq(address[BANK_SELECT_WIDTH:]),
                        stage_payload.eq(payload),
                    ]

    # Register forward requests for the next cycle. / 为下一周期寄存转发请求。
    def register_forward_requests(self, module: Module) -> list[tuple[Any, Any]]:
        """Return one delayed request pair per forward port. / 返回每个转发端口的一对延迟请求。"""

        requests: list[tuple[Any, Any]] = []
        for forward in range(3):
            first_bits: list[Signal] = []
            second_bits: list[Signal] = []
            for entry in range(ENTRY_COUNT):
                state_index = forward * ENTRY_COUNT + entry
                suffix = f"_{state_index}" if state_index else ""
                first_bits.append(Signal(name=f"needCheck0Reg{suffix}", reset_less=True))
                second_bits.append(Signal(name=f"needCheck1Reg{suffix}", reset_less=True))
                module.d.sync += [
                    first_bits[entry].eq(self.ports[f"io_needForward_{forward}_0"][entry]),
                    second_bits[entry].eq(self.ports[f"io_needForward_{forward}_1"][entry]),
                ]
            requests.append((Cat(*first_bits), Cat(*second_bits)))
        return requests

    # Resolve one byte-style forward request. / 解析一个字节式转发请求。
    def select_forward(self, data: Array, valid: Array, request: tuple[Any, Any]) -> tuple[Any, Any]:
        """Return valid and data with half-one priority. / 返回带 half-one 优先级的有效位和数据。"""

        forward_valid: Any = Const(0, 1)
        forward_data: Any = data[0]
        for half in range(2):
            for entry in range(ENTRY_COUNT):
                match = request[half][entry] & valid[entry]
                forward_valid = forward_valid | match
                forward_data = Mux(match, data[entry], forward_data)
        return forward_valid, forward_data

    # Resolve one byte of a wide forward request. / 解析宽转发请求的一个字节。
    def select_forward_byte(
        self,
        data: Array,
        mask: Array,
        request: tuple[Any, Any],
        byte: int,
    ) -> tuple[Any, Any]:
        """Return one byte's valid bit and selected data. / 返回一个字节的有效位和选中数据。"""

        forward_valid: Any = Const(0, 1)
        forward_data: Any = data[0][byte * 8:(byte + 1) * 8]
        for half in range(2):
            for entry in range(ENTRY_COUNT):
                match = request[half][entry] & mask[entry][byte]
                forward_valid = forward_valid | match
                forward_data = Mux(match, data[entry][byte * 8:(byte + 1) * 8], forward_data)
        return forward_valid, forward_data

    # Build an address CAM specialization. / 构建地址 CAM 特化。
    def elaborate_addr(self, module: Module) -> None:
        """Implement synchronous reads, writes, and line forwarding. / 实现同步读写和 cacheline 转发。"""

        data_width = 48 if self.member == "SQAddrModule" else 50
        data = Array(Signal(data_width, name=f"data_{entry}", reset_less=True) for entry in range(ENTRY_COUNT))
        mask = Array(Signal(BYTE_COUNT, name=f"mask_{entry}", reset_less=True) for entry in range(ENTRY_COUNT))
        lineflag = Array(Signal(name=f"lineflag_{entry}", reset_less=True) for entry in range(ENTRY_COUNT))

        for entry in range(ENTRY_COUNT):
            with cast(Any, module.If(self.ports["io_wen_1"] & (self.ports["io_waddr_1"] == entry))):
                module.d.sync += [
                    data[entry].eq(self.ports["io_wdata_1"]),
                    mask[entry].eq(self.ports["io_wmask_1"]),
                    lineflag[entry].eq(self.ports["io_wlineflag_1"]),
                ]
            with cast(Any, module.Elif(self.ports["io_wen_0"] & (self.ports["io_waddr_0"] == entry))):
                module.d.sync += [
                    data[entry].eq(self.ports["io_wdata_0"]),
                    mask[entry].eq(self.ports["io_wmask_0"]),
                    lineflag[entry].eq(self.ports["io_wlineflag_0"]),
                ]

        for read in range(2):
            data_address = Signal(ADDRESS_WIDTH, name=f"io_rdata_{read}_next_r")
            data_address_input = self.ports[f"io_raddr_{read}"]
            with cast(Any, module.If(data_address_input != data_address)):
                module.d.sync += data_address.eq(data_address_input)
            module.d.comb += self.ports[f"io_rdata_{read}"].eq(
                self.read_entry(data, data_address)
            )
            if self.member == "SQAddrModule":
                lineflag_address = Signal(ADDRESS_WIDTH, name=f"io_rlineflag_{read}_next_r")
                with cast(Any, module.If(data_address_input != lineflag_address)):
                    module.d.sync += lineflag_address.eq(data_address_input)
                module.d.comb += self.ports[f"io_rlineflag_{read}"].eq(
                    self.read_entry(lineflag, lineflag_address)
                )

        for forward in range(3):
            query = self.ports[f"io_forwardMdata_{forward}"]
            query_mask = self.ports[f"io_forwardDataMask_{forward}"]
            for entry in range(ENTRY_COUNT):
                line_hit = query[6:data_width] == data[entry][6:data_width]
                word_hit = query[4:6] == data[entry][4:6]
                mask_hit = (query_mask & mask[entry]).any()
                hit = line_hit & (lineflag[entry] | (word_hit & mask_hit))
                module.d.comb += self.ports[f"io_forwardMmask_{forward}_{entry}"].eq(hit)

    # Build the byte data specialization. / 构建字节数据特化。
    def elaborate_data8(self, module: Module) -> None:
        """Implement banked byte storage, reads, and forwarding. / 实现分 bank 字节存储、读取和转发。"""

        data = Array(Signal(8, name=f"data_{entry}_data", reset_less=True) for entry in range(ENTRY_COUNT))
        valid = Array(Signal(name=f"data_{entry}_valid", reset_less=True) for entry in range(ENTRY_COUNT))
        self.add_banked_write_pipeline(module, data, "io_data", "data", 0, 8)
        self.add_banked_write_pipeline(module, valid, "io_mask", "mask", 2, 1)

        for read in range(2):
            address = Signal(ADDRESS_WIDTH, name=f"io_rdata_{read}_REG", reset_less=True)
            module.d.sync += address.eq(self.ports[f"io_raddr_{read}"])
            module.d.comb += [
                self.ports[f"io_rdata_{read}_valid"].eq(self.read_entry(valid, address)),
                self.ports[f"io_rdata_{read}_data"].eq(self.read_entry(data, address)),
            ]

        for forward, request in enumerate(self.register_forward_requests(module)):
            forward_valid, forward_data = self.select_forward(data, valid, request)
            module.d.comb += [
                self.ports[f"io_forwardValid_{forward}"].eq(forward_valid),
                self.ports[f"io_forwardData_{forward}"].eq(forward_data),
            ]

    # Build the wide data specialization. / 构建宽数据特化。
    def elaborate_data(self, module: Module) -> None:
        """Implement banked wide storage, reads, and byte forwarding. / 实现分 bank 宽存储、读取和字节转发。"""

        # Scala SQDataModule is a sixteen-lane SQData8Module wrapper. /
        # Scala SQDataModule 是十六个 SQData8Module 的封装。
        lanes: list[StoreQueueDataFamily] = []
        for byte in range(BYTE_COUNT):
            lane = StoreQueueDataFamily("SQData8Module")
            module.submodules[f"data8_{byte}"] = lane
            lanes.append(lane)
            module.d.comb += [lane.ports["clock"].eq(self.clock), lane.ports["reset"].eq(self.reset)]

            for write in range(2):
                module.d.comb += [
                    lane.ports[f"io_data_wen_{write}"].eq(self.ports[f"io_data_wen_{write}"]),
                    lane.ports[f"io_data_waddr_{write}"].eq(self.ports[f"io_data_waddr_{write}"]),
                    lane.ports[f"io_data_wdata_{write}"].eq(
                        self.ports[f"io_data_wdata_{write}"][byte * 8:(byte + 1) * 8]
                    ),
                    lane.ports[f"io_mask_wen_{write}"].eq(self.ports[f"io_mask_wen_{write}"]),
                    lane.ports[f"io_mask_waddr_{write}"].eq(self.ports[f"io_mask_waddr_{write}"]),
                    lane.ports[f"io_mask_wdata_{write}"].eq(
                        self.ports[f"io_mask_wdata_{write}"][byte]
                    ),
                ]
            for read in range(2):
                module.d.comb += lane.ports[f"io_raddr_{read}"].eq(self.ports[f"io_raddr_{read}"])
            for forward in range(3):
                for half in range(2):
                    module.d.comb += lane.ports[f"io_needForward_{forward}_{half}"].eq(
                        self.ports[f"io_needForward_{forward}_{half}"]
                    )

        for read in range(2):
            module.d.comb += [
                self.ports[f"io_rdata_{read}_mask"].eq(
                    Cat(*(lane.ports[f"io_rdata_{read}_valid"] for lane in lanes))
                ),
                self.ports[f"io_rdata_{read}_data"].eq(
                    Cat(*(lane.ports[f"io_rdata_{read}_data"] for lane in lanes))
                ),
            ]
        for forward in range(3):
            for byte, lane in enumerate(lanes):
                module.d.comb += [
                    self.ports[f"io_forwardMask_{forward}_{byte}"].eq(
                        lane.ports[f"io_forwardValid_{forward}"]
                    ),
                    self.ports[f"io_forwardData_{forward}_{byte}"].eq(
                        lane.ports[f"io_forwardData_{forward}"]
                    ),
                ]

    # Elaborate the selected specialization. / 展开选定特化。
    def elaborate(self, platform: Any) -> Module:
        """Return the selected address or data circuit. / 返回选定的地址或数据电路。"""

        del platform
        module = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        module.domains += domain
        if self.member.startswith("SQAddr"):
            self.elaborate_addr(module)
        elif self.member == "SQData8Module":
            self.elaborate_data8(module)
        else:
            self.elaborate_data(module)
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Export one selected specialization. / 导出一个选定特化。
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    """Return deterministic same-name Verilog. / 返回确定性的同名 Verilog。"""

    del injected_dependencies
    member = "SQAddrModule"
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = StoreQueueDataFamily(member)
    return verilog.convert(top, name=member, ports=[top.ports[name] for name, _direction, _width in top.specs], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default specialization. / 打印默认特化。
def main() -> None:
    """Print the default address specialization. / 打印默认地址特化。"""

    print(build_verilog({"module": "SQAddrModule"}, {}))


if __name__ == "__main__":
    main()
