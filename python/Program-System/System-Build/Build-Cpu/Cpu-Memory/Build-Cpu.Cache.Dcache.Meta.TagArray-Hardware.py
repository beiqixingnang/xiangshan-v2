"""Locked Kunminghu V2 four-way data-cache tag array.
锁定昆明湖 V2 四路数据缓存标签阵列。

The public surface includes the two MBIST bore bundles and the two SRAM DFT
bundles emitted by the locked DefaultConfig XSTop. Internally each two-way
bank models reset scrub, normal arbitration, MBIST override, masked storage,
and delayed MBIST readback.
"""

from __future__ import annotations

from typing import Any, cast

from amaranth import Array, Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = ["COVERED_MODULES", "SOURCE_PATHS", "PORT_SPECS", "TagArray", "build_verilog", "main"]

COVERED_MODULES: tuple[str, ...] = ("TagArray",)

SOURCE_PATHS: tuple[str, ...] = (
    "upstream/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala",
    "upstream/utility/src/main/scala/utility/sram/SRAMTemplate.scala",
    "upstream/utility/src/main/scala/utility/sram/SramProto.scala",
    "upstream/utility/src/main/scala/utility/mbist/MbistClockGateCell.scala",
)

PORT_SPECS: tuple[tuple[str, str, int], ...] = (
    ("clock", "input", 1), ("reset", "input", 1),
    ("io_read_ready", "output", 1), ("io_read_valid", "input", 1),
    ("io_read_bits_idx", "input", 8),
    ("io_resp_0", "output", 43), ("io_resp_1", "output", 43),
    ("io_resp_2", "output", 43), ("io_resp_3", "output", 43),
    ("io_write_valid", "input", 1), ("io_write_bits_idx", "input", 8),
    ("io_write_bits_way_en", "input", 4),
    ("io_write_bits_tag", "input", 36), ("io_write_bits_ecc", "input", 7),
    ("boreChildrenBd_bore_addr", "input", 9),
    ("boreChildrenBd_bore_addr_rd", "input", 9),
    ("boreChildrenBd_bore_wdata", "input", 86),
    ("boreChildrenBd_bore_wmask", "input", 2),
    ("boreChildrenBd_bore_re", "input", 1),
    ("boreChildrenBd_bore_we", "input", 1),
    ("boreChildrenBd_bore_rdata", "output", 86),
    ("boreChildrenBd_bore_ack", "input", 1),
    ("boreChildrenBd_bore_selectedOH", "input", 1),
    ("boreChildrenBd_bore_array", "input", 6),
    ("boreChildrenBd_bore_1_addr", "input", 9),
    ("boreChildrenBd_bore_1_addr_rd", "input", 9),
    ("boreChildrenBd_bore_1_wdata", "input", 86),
    ("boreChildrenBd_bore_1_wmask", "input", 2),
    ("boreChildrenBd_bore_1_re", "input", 1),
    ("boreChildrenBd_bore_1_we", "input", 1),
    ("boreChildrenBd_bore_1_rdata", "output", 86),
    ("boreChildrenBd_bore_1_ack", "input", 1),
    ("boreChildrenBd_bore_1_selectedOH", "input", 1),
    ("boreChildrenBd_bore_1_array", "input", 6),
    ("sigFromSrams_bore_ram_hold", "input", 1),
    ("sigFromSrams_bore_ram_bypass", "input", 1),
    ("sigFromSrams_bore_ram_bp_clken", "input", 1),
    ("sigFromSrams_bore_ram_aux_clk", "input", 1),
    ("sigFromSrams_bore_ram_aux_ckbp", "input", 1),
    ("sigFromSrams_bore_ram_mcp_hold", "input", 1),
    ("sigFromSrams_bore_cgen", "input", 1),
    ("sigFromSrams_bore_1_ram_hold", "input", 1),
    ("sigFromSrams_bore_1_ram_bypass", "input", 1),
    ("sigFromSrams_bore_1_ram_bp_clken", "input", 1),
    ("sigFromSrams_bore_1_ram_aux_clk", "input", 1),
    ("sigFromSrams_bore_1_ram_aux_ckbp", "input", 1),
    ("sigFromSrams_bore_1_ram_mcp_hold", "input", 1),
    ("sigFromSrams_bore_1_cgen", "input", 1),
)


# =============================================================================
# Implementation
# =============================================================================
class TagArray(Elaboratable):
    """Four-way tag array with two exact two-way SRAM banks. / 两个双路 bank 构成的四路标签阵列。"""

    def __init__(self) -> None:
        """Allocate the exact locked public port surface. / 分配精确锁定的公共端口。"""

        self.ports: dict[str, Signal] = {
            name: Signal(width, name=name) for name, _direction, width in PORT_SPECS
        }

    def _port(self, bank: int, family: str, field: str) -> Signal:
        """Return one bank-specific MBIST or DFT signal. / 返回 bank 专属 MBIST 或 DFT 信号。"""

        infix = "" if bank == 0 else "_1"
        return self.ports[f"{family}{infix}_{field}"]

    def _bank(self, module: Module, bank: int) -> tuple[Any, Any, Any]:
        """Elaborate one locked TagSRAMBank transition relation. / 展开一个 TagSRAMBank 状态转移。"""

        p = self.ports
        prefix = f"tag_arrays_{bank}"
        rst_cnt = Signal(9, reset=0, name=f"{prefix}.rst_cnt")
        resp_reg = Signal(reset=0, name=f"{prefix}.tag_array.respReg")
        rdata_reg = Signal(86, reset_less=True, name=f"{prefix}.tag_array.rdataReg")
        read_addr = Signal(8, reset_less=True,
                           name=f"{prefix}.tag_array.array.array_ext._RW0_raddr_d0")
        read_enable = Signal(reset_less=True,
                             name=f"{prefix}.tag_array.array.array_ext._RW0_ren_d0")
        read_mode = Signal(reset_less=True,
                           name=f"{prefix}.tag_array.array.array_ext._RW0_rmode_d0")
        memory = Array(
            Signal(86, reset_less=True,
                   name=f"{prefix}.tag_array.array.array_ext.Memory[{index}]")
            for index in range(256)
        )

        reset_done = cast(Any, rst_cnt[8])
        normal_write = ~reset_done | p["io_write_valid"]
        read_ready = ~normal_write
        mbist_ack = self._port(bank, "boreChildrenBd_bore", "ack")
        mbist_read = self._port(bank, "boreChildrenBd_bore", "re")
        mbist_write = self._port(bank, "boreChildrenBd_bore", "we")
        read_clock_enable = Mux(mbist_ack, mbist_read,
                                read_ready & p["io_read_valid"])
        write_clock_enable = Mux(mbist_ack, mbist_write, normal_write)
        hold = self._port(bank, "sigFromSrams_bore", "ram_hold")
        final_write = write_clock_enable & ~hold
        gate_enable = (
            self._port(bank, "sigFromSrams_bore", "cgen")
            | Mux(mbist_ack, mbist_read | mbist_write,
                  read_clock_enable | write_clock_enable)
        )

        normal_write_addr = Mux(reset_done, p["io_write_bits_idx"], rst_cnt[:8])
        selected_addr = Mux(
            mbist_ack,
            self._port(bank, "boreChildrenBd_bore", "addr_rd")[:8],
            Mux(final_write, normal_write_addr, p["io_read_bits_idx"]),
        )
        encoded = Cat(p["io_write_bits_tag"], p["io_write_bits_ecc"])
        normal_data = Mux(reset_done, Cat(encoded, encoded), Const(0, 86))
        write_data = Mux(mbist_ack,
                         self._port(bank, "boreChildrenBd_bore", "wdata"),
                         normal_data)
        normal_way_mask = Mux(
            reset_done,
            p["io_write_bits_way_en"][bank * 2:bank * 2 + 2],
            Const(3, 2),
        )
        mbist_mask = Mux(
            self._port(bank, "boreChildrenBd_bore", "selectedOH"),
            self._port(bank, "boreChildrenBd_bore", "wmask"),
            Const(0, 2),
        )
        write_mask = Mux(mbist_ack, mbist_mask, normal_way_mask)
        memory_output = memory[read_addr]

        with cast(Any, module.If(~reset_done)):
            module.d.sync += rst_cnt.eq(rst_cnt + 1)
        module.d.sync += resp_reg.eq(read_clock_enable)
        with cast(Any, module.If(resp_reg)):
            module.d.sync += rdata_reg.eq(memory_output)
        with cast(Any, module.If(gate_enable)):
            module.d.sync += [read_addr.eq(selected_addr),
                              read_enable.eq(final_write | read_clock_enable),
                              read_mode.eq(final_write)]
            with cast(Any, module.If(final_write)):
                with cast(Any, module.If(write_mask[0])):
                    module.d.sync += memory[selected_addr][:43].eq(write_data[:43])
                with cast(Any, module.If(write_mask[1])):
                    module.d.sync += memory[selected_addr][43:].eq(write_data[43:])

        module.d.comb += self._port(bank, "boreChildrenBd_bore", "rdata").eq(rdata_reg)
        return read_ready, memory_output[:43], memory_output[43:]

    def elaborate(self, platform: Any) -> Module:
        """Elaborate both banks and expose the four-way response. / 展开两个 bank 并导出四路响应。"""

        del platform
        module = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.ports["clock"]
        domain.rst = self.ports["reset"]
        module.domains.sync = domain
        _ready0, resp0, resp1 = self._bank(module, 0)
        ready1, resp2, resp3 = self._bank(module, 1)
        module.d.comb += [
            self.ports["io_read_ready"].eq(ready1),
            self.ports["io_resp_0"].eq(resp0), self.ports["io_resp_1"].eq(resp1),
            self.ports["io_resp_2"].eq(resp2), self.ports["io_resp_3"].eq(resp3),
        ]
        return module


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: Any = None, injected_dependencies: Any = None) -> str:
    """Emit the exact locked TagArray top. / 导出精确锁定 TagArray 顶层。"""

    del configuration, injected_dependencies
    top = TagArray()
    return verilog.convert(top, name="TagArray",
                           ports=[top.ports[name] for name, _direction, _width in PORT_SPECS],
                           emit_src=False)


def main() -> None:
    """Print the deterministic locked export. / 打印确定性的锁定导出。"""

    print(build_verilog())


if __name__ == "__main__":
    main()
