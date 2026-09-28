"""DCache asynchronous metadata-array family.
DCache 异步元数据阵列族。
"""

from __future__ import annotations

from typing import Any, cast

from amaranth import Array, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = ["COVERED_MODULES", "DcacheMetaArrayFamily", "build_verilog", "main"]

COVERED_MODULES: tuple[str, ...] = (
    "L1CohMetaArray", "L1ErrorMetaArray", "L1FlagMetaArray", "L1PrefetchSourceArray",
)


PortSpec = tuple[str, str, int]

PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    'L1CohMetaArray': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_read_0_valid', 'input', 1),
        ('io_read_0_bits_idx', 'input', 8),
        ('io_read_1_valid', 'input', 1),
        ('io_read_1_bits_idx', 'input', 8),
        ('io_read_2_valid', 'input', 1),
        ('io_read_2_bits_idx', 'input', 8),
        ('io_read_3_valid', 'input', 1),
        ('io_read_3_bits_idx', 'input', 8),
        ('io_resp_0_0_coh_state', 'output', 2),
        ('io_resp_0_1_coh_state', 'output', 2),
        ('io_resp_0_2_coh_state', 'output', 2),
        ('io_resp_0_3_coh_state', 'output', 2),
        ('io_resp_1_0_coh_state', 'output', 2),
        ('io_resp_1_1_coh_state', 'output', 2),
        ('io_resp_1_2_coh_state', 'output', 2),
        ('io_resp_1_3_coh_state', 'output', 2),
        ('io_resp_2_0_coh_state', 'output', 2),
        ('io_resp_2_1_coh_state', 'output', 2),
        ('io_resp_2_2_coh_state', 'output', 2),
        ('io_resp_2_3_coh_state', 'output', 2),
        ('io_resp_3_0_coh_state', 'output', 2),
        ('io_resp_3_1_coh_state', 'output', 2),
        ('io_resp_3_2_coh_state', 'output', 2),
        ('io_resp_3_3_coh_state', 'output', 2),
        ('io_write_0_valid', 'input', 1),
        ('io_write_0_bits_idx', 'input', 8),
        ('io_write_0_bits_way_en', 'input', 4),
        ('io_write_0_bits_meta_coh_state', 'input', 2),
    ),
    'L1ErrorMetaArray': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_read_0_valid', 'input', 1),
        ('io_read_0_bits_idx', 'input', 8),
        ('io_read_1_valid', 'input', 1),
        ('io_read_1_bits_idx', 'input', 8),
        ('io_read_2_valid', 'input', 1),
        ('io_read_2_bits_idx', 'input', 8),
        ('io_read_3_valid', 'input', 1),
        ('io_read_3_bits_idx', 'input', 8),
        ('io_resp_0_0_tl_denied', 'output', 1),
        ('io_resp_0_0_tl_corrupt', 'output', 1),
        ('io_resp_0_1_tl_denied', 'output', 1),
        ('io_resp_0_1_tl_corrupt', 'output', 1),
        ('io_resp_0_2_tl_denied', 'output', 1),
        ('io_resp_0_2_tl_corrupt', 'output', 1),
        ('io_resp_0_3_tl_denied', 'output', 1),
        ('io_resp_0_3_tl_corrupt', 'output', 1),
        ('io_resp_1_0_tl_denied', 'output', 1),
        ('io_resp_1_0_tl_corrupt', 'output', 1),
        ('io_resp_1_1_tl_denied', 'output', 1),
        ('io_resp_1_1_tl_corrupt', 'output', 1),
        ('io_resp_1_2_tl_denied', 'output', 1),
        ('io_resp_1_2_tl_corrupt', 'output', 1),
        ('io_resp_1_3_tl_denied', 'output', 1),
        ('io_resp_1_3_tl_corrupt', 'output', 1),
        ('io_resp_2_0_tl_denied', 'output', 1),
        ('io_resp_2_0_tl_corrupt', 'output', 1),
        ('io_resp_2_1_tl_denied', 'output', 1),
        ('io_resp_2_1_tl_corrupt', 'output', 1),
        ('io_resp_2_2_tl_denied', 'output', 1),
        ('io_resp_2_2_tl_corrupt', 'output', 1),
        ('io_resp_2_3_tl_denied', 'output', 1),
        ('io_resp_2_3_tl_corrupt', 'output', 1),
        ('io_resp_3_0_tl_denied', 'output', 1),
        ('io_resp_3_0_tl_corrupt', 'output', 1),
        ('io_resp_3_1_tl_denied', 'output', 1),
        ('io_resp_3_1_tl_corrupt', 'output', 1),
        ('io_resp_3_2_tl_denied', 'output', 1),
        ('io_resp_3_2_tl_corrupt', 'output', 1),
        ('io_resp_3_3_tl_denied', 'output', 1),
        ('io_resp_3_3_tl_corrupt', 'output', 1),
        ('io_write_0_valid', 'input', 1),
        ('io_write_0_bits_idx', 'input', 8),
        ('io_write_0_bits_way_en', 'input', 4),
        ('io_write_0_bits_error_tl_denied', 'input', 1),
        ('io_write_0_bits_error_tl_corrupt', 'input', 1),
    ),
    'L1FlagMetaArray': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_read_3_valid', 'input', 1),
        ('io_read_3_bits_idx', 'input', 8),
        ('io_read_4_valid', 'input', 1),
        ('io_read_4_bits_idx', 'input', 8),
        ('io_resp_3_0', 'output', 1),
        ('io_resp_3_1', 'output', 1),
        ('io_resp_3_2', 'output', 1),
        ('io_resp_3_3', 'output', 1),
        ('io_resp_4_0', 'output', 1),
        ('io_resp_4_1', 'output', 1),
        ('io_resp_4_2', 'output', 1),
        ('io_resp_4_3', 'output', 1),
        ('io_write_0_valid', 'input', 1),
        ('io_write_0_bits_idx', 'input', 8),
        ('io_write_0_bits_way_en', 'input', 4),
        ('io_write_1_valid', 'input', 1),
        ('io_write_1_bits_idx', 'input', 8),
        ('io_write_1_bits_way_en', 'input', 4),
        ('io_write_2_valid', 'input', 1),
        ('io_write_2_bits_idx', 'input', 8),
        ('io_write_2_bits_way_en', 'input', 4),
        ('io_write_3_valid', 'input', 1),
        ('io_write_3_bits_idx', 'input', 8),
        ('io_write_3_bits_way_en', 'input', 4),
        ('io_write_3_bits_flag', 'input', 1),
    ),
    'L1PrefetchSourceArray': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_read_0_valid', 'input', 1),
        ('io_read_0_bits_idx', 'input', 8),
        ('io_read_1_valid', 'input', 1),
        ('io_read_1_bits_idx', 'input', 8),
        ('io_read_2_valid', 'input', 1),
        ('io_read_2_bits_idx', 'input', 8),
        ('io_read_3_valid', 'input', 1),
        ('io_read_3_bits_idx', 'input', 8),
        ('io_read_4_valid', 'input', 1),
        ('io_read_4_bits_idx', 'input', 8),
        ('io_resp_0_0', 'output', 3),
        ('io_resp_0_1', 'output', 3),
        ('io_resp_0_2', 'output', 3),
        ('io_resp_0_3', 'output', 3),
        ('io_resp_1_0', 'output', 3),
        ('io_resp_1_1', 'output', 3),
        ('io_resp_1_2', 'output', 3),
        ('io_resp_1_3', 'output', 3),
        ('io_resp_2_0', 'output', 3),
        ('io_resp_2_1', 'output', 3),
        ('io_resp_2_2', 'output', 3),
        ('io_resp_2_3', 'output', 3),
        ('io_resp_3_0', 'output', 3),
        ('io_resp_3_1', 'output', 3),
        ('io_resp_3_2', 'output', 3),
        ('io_resp_3_3', 'output', 3),
        ('io_resp_4_0', 'output', 3),
        ('io_resp_4_1', 'output', 3),
        ('io_resp_4_2', 'output', 3),
        ('io_resp_4_3', 'output', 3),
        ('io_write_0_valid', 'input', 1),
        ('io_write_0_bits_idx', 'input', 8),
        ('io_write_0_bits_way_en', 'input', 4),
        ('io_write_1_valid', 'input', 1),
        ('io_write_1_bits_idx', 'input', 8),
        ('io_write_1_bits_way_en', 'input', 4),
        ('io_write_2_valid', 'input', 1),
        ('io_write_2_bits_idx', 'input', 8),
        ('io_write_2_bits_way_en', 'input', 4),
        ('io_write_3_valid', 'input', 1),
        ('io_write_3_bits_idx', 'input', 8),
        ('io_write_3_bits_way_en', 'input', 4),
        ('io_write_3_bits_source', 'input', 3),
    ),
}

READ_INDICES: dict[str, tuple[int, ...]] = {
    "L1CohMetaArray": (0, 1, 2, 3),
    "L1ErrorMetaArray": (0, 1, 2, 3),
    "L1FlagMetaArray": (3, 4),
    "L1PrefetchSourceArray": (0, 1, 2, 3, 4),
}

WRITE_INDICES: dict[str, tuple[int, ...]] = {
    "L1CohMetaArray": (0,),
    "L1ErrorMetaArray": (0,),
    "L1FlagMetaArray": (0, 1, 2, 3),
    "L1PrefetchSourceArray": (0, 1, 2, 3),
}


# =============================================================================
# Implementation
# =============================================================================
class DcacheMetaArrayFamily(Elaboratable):
    """One four-way metadata array specialization. / 一个四路元数据阵列特化。"""

    # Initialize the declared member interface. / 初始化声明的成员接口。
    def __init__(self, member: str = "L1CohMetaArray") -> None:
        """Declare the member ports. / 声明成员端口。"""

        if member not in PORT_SPECS:
            raise ValueError(f"unsupported DCache metadata member: {member}")
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports: dict[str, Signal] = {
            name: Signal(width, name=name) for name, _direction, width in self.specs
        }
        self.clock = self.ports["clock"]
        self.reset = self.ports["reset"]

    # Return the member field layout. / 返回成员字段布局。
    def field_layout(self) -> tuple[tuple[str, int, str], ...]:
        """Map read suffix, width, and write suffix. / 映射读取后缀、位宽与写入后缀。"""

        if self.member == "L1CohMetaArray":
            return (("coh_state", 2, "meta_coh_state"),)
        if self.member == "L1ErrorMetaArray":
            return (("tl_denied", 1, "error_tl_denied"), ("tl_corrupt", 1, "error_tl_corrupt"))
        if self.member == "L1FlagMetaArray":
            return (("", 1, "flag"),)
        return (("", 3, "source"),)

    # Return the member bypass timing. / 返回成员旁路时序。
    def bypass_style(self) -> str:
        """Identify the read-path write stages. / 标识读取路径的写入级。"""

        if self.member in {"L1CohMetaArray", "L1ErrorMetaArray"}:
            return "s0_s1"
        if self.member == "L1PrefetchSourceArray":
            return "s1"
        return "none"

    # Elaborate the four-way storage. / 展开四路存储。
    def elaborate(self, platform: Any) -> Module:
        """Implement staged writes and member-specific reads. / 实现分级写入和成员专属读取。"""

        del platform
        module = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        module.domains += domain
        layouts = self.field_layout()
        writes = WRITE_INDICES[self.member]
        style = self.bypass_style()
        memories = {
            read_suffix: tuple(
                Array(
                    Signal(width, name=f"meta_{read_suffix or 'value'}_{way}_{index}", reset=0)
                    for index in range(256)
                )
                for way in range(4)
            )
            for read_suffix, width, _write_suffix in layouts
        }
        stage_enable: dict[tuple[int, int], Signal] = {}
        stage_address: dict[tuple[int, int], Signal] = {}
        stage_data: dict[tuple[str, int, int], Signal] = {}

        for way in range(4):
            for write in writes:
                stage_enable[way, write] = Signal(
                    name=f"meta_s1_enable_{way}_{write}", reset_less=True
                )
                stage_address[way, write] = Signal(
                    8, name=f"meta_s1_address_{way}_{write}", reset_less=True
                )
                for read_suffix, width, write_suffix in layouts:
                    data_name = f"io_write_{write}_bits_{write_suffix}"
                    if data_name in self.ports:
                        stage_data[read_suffix, way, write] = Signal(
                            width,
                            name=f"meta_s1_{read_suffix or 'value'}_{way}_{write}",
                            reset_less=True,
                        )

        for write in writes:
            valid = self.ports[f"io_write_{write}_valid"]
            address = self.ports[f"io_write_{write}_bits_idx"]
            enables = self.ports[f"io_write_{write}_bits_way_en"]
            for way in range(4):
                enabled = valid & enables[way]
                module.d.sync += stage_enable[way, write].eq(enabled)
                with cast(Any, module.If(enabled)):
                    module.d.sync += stage_address[way, write].eq(address)
                    for read_suffix, _width, write_suffix in layouts:
                        data_name = f"io_write_{write}_bits_{write_suffix}"
                        data_register = stage_data.get((read_suffix, way, write))
                        if data_register is not None:
                            module.d.sync += data_register.eq(self.ports[data_name])

        for read_suffix, width, _write_suffix in layouts:
            for way in range(4):
                for index in range(256):
                    cell = memories[read_suffix][way][index]
                    next_value = cell
                    for write in writes:
                        staged_value = stage_data.get((read_suffix, way, write))
                        if staged_value is None:
                            staged_value = Const(1, width)
                        matches_cell = stage_enable[way, write] & (stage_address[way, write] == index)
                        next_value = Mux(matches_cell, staged_value, next_value)
                    module.d.sync += cell.eq(next_value)

        for read in READ_INDICES[self.member]:
            valid = self.ports[f"io_read_{read}_valid"]
            address = self.ports[f"io_read_{read}_bits_idx"]
            for way in range(4):
                if style == "none":
                    registered_address = Signal(
                        8, name=f"meta_read_address_{read}_{way}", reset_less=True
                    )
                    with cast(Any, module.If(valid)):
                        module.d.sync += registered_address.eq(address)
                    for read_suffix, _width, _write_suffix in layouts:
                        suffix = f"_{read_suffix}" if read_suffix else ""
                        module.d.comb += self.ports[f"io_resp_{read}_{way}{suffix}"].eq(
                            memories[read_suffix][way][registered_address]
                        )
                    continue

                bypass_hit = Const(0)
                bypass_values: dict[str, Any] = {
                    read_suffix: Const(0, width) for read_suffix, width, _write_suffix in layouts
                }
                for write in writes:
                    staged_match = stage_enable[way, write] & (stage_address[way, write] == address)
                    bypass_hit = bypass_hit | staged_match
                    for read_suffix, width, _write_suffix in layouts:
                        staged_value = stage_data.get((read_suffix, way, write))
                        if staged_value is None:
                            staged_value = Const(1, width)
                        bypass_values[read_suffix] = Mux(
                            staged_match, staged_value, bypass_values[read_suffix]
                        )
                    if style == "s0_s1":
                        current_match = (
                            self.ports[f"io_write_{write}_valid"]
                            & self.ports[f"io_write_{write}_bits_way_en"][way]
                            & (self.ports[f"io_write_{write}_bits_idx"] == address)
                        )
                        bypass_hit = bypass_hit | current_match
                        for read_suffix, _width, write_suffix in layouts:
                            current_value = self.ports[f"io_write_{write}_bits_{write_suffix}"]
                            bypass_values[read_suffix] = Mux(
                                current_match, current_value, bypass_values[read_suffix]
                            )

                registered_bypass = Signal(
                    name=f"meta_read_bypass_{read}_{way}", reset_less=True
                )
                with cast(Any, module.If(valid)):
                    module.d.sync += registered_bypass.eq(bypass_hit)
                bypass_registers: dict[str, Signal] = {}
                for read_suffix, width, _write_suffix in layouts:
                    bypass_registers[read_suffix] = Signal(
                        width,
                        name=f"meta_read_bypass_data_{read}_{way}_{read_suffix or 'value'}",
                        reset_less=True,
                    )
                    with cast(Any, module.If(bypass_hit)):
                        module.d.sync += bypass_registers[read_suffix].eq(bypass_values[read_suffix])

                if style == "s0_s1":
                    for read_suffix, width, _write_suffix in layouts:
                        memory_register = Signal(
                            width,
                            name=f"meta_read_data_{read}_{way}_{read_suffix or 'value'}",
                            reset_less=True,
                        )
                        with cast(Any, module.If(valid)):
                            module.d.sync += memory_register.eq(memories[read_suffix][way][address])
                        suffix = f"_{read_suffix}" if read_suffix else ""
                        module.d.comb += self.ports[f"io_resp_{read}_{way}{suffix}"].eq(
                            Mux(registered_bypass, bypass_registers[read_suffix], memory_register)
                        )
                else:
                    registered_address = Signal(
                        8, name=f"meta_read_address_{read}_{way}", reset_less=True
                    )
                    with cast(Any, module.If(valid)):
                        module.d.sync += registered_address.eq(address)
                    for read_suffix, _width, _write_suffix in layouts:
                        suffix = f"_{read_suffix}" if read_suffix else ""
                        module.d.comb += self.ports[f"io_resp_{read}_{way}{suffix}"].eq(
                            Mux(
                                registered_bypass,
                                bypass_registers[read_suffix],
                                memories[read_suffix][way][registered_address],
                            )
                        )
        return module


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    """Export one deterministic same-name metadata member. / 导出确定性的同名元数据成员。"""

    del injected_dependencies
    member = "L1CohMetaArray"
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = DcacheMetaArrayFamily(member)
    return verilog.convert(top, name=member, ports=[top.ports[n] for n, _d, _w in top.specs], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the coherent metadata member. / 打印一致性元数据成员。"""

    print(build_verilog({"module": "L1CohMetaArray"}, {}))


if __name__ == "__main__":
    main()
