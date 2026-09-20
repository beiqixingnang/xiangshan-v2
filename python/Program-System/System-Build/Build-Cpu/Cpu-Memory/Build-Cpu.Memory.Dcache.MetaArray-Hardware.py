"""UHSC V2 asynchronous DCache metadata-array family.
昆明湖 V2 异步 DCache 元数据阵列 family。

Four source specializations share the same four-way array geometry and
one-cycle registered writes.  This aggregate keeps their locked flattened
ports while implementing coherent-state, error, flag, and prefetch-source
storage with per-way write enables and registered read addresses.
"""

from __future__ import annotations

from typing import Any, cast

from amaranth import Array, ClockDomain, Elaboratable, Module, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = ["COVERED_MODULES", "DcacheMetaArrayFamily", "build_verilog", "main"]

COVERED_MODULES: tuple[str, ...] = (
    "L1CohMetaArray", "L1ErrorMetaArray", "L1FlagMetaArray", "L1PrefetchSourceArray",
)


# =============================================================================
# Configuration
# =============================================================================
def read_ports(indices: tuple[int, ...], width: int, fields: tuple[tuple[str, int], ...]) -> list[tuple[str, str, int]]:
    """Construct flattened read request and response ports. / 构造扁平读取请求与响应端口。"""

    ports: list[tuple[str, str, int]] = []
    for read in indices:
        ports.extend(((f"io_read_{read}_valid", "input", 1), (f"io_read_{read}_bits_idx", "input", 8)))
    for read in indices:
        for way in range(4):
            for field, field_width in fields:
                suffix = f"_{field}" if field else ""
                ports.append((f"io_resp_{read}_{way}{suffix}", "output", field_width or width))
    return ports


def write_ports(indices: tuple[int, ...], fields: tuple[tuple[str, int], ...]) -> list[tuple[str, str, int]]:
    """Construct flattened metadata write ports. / 构造扁平元数据写入端口。"""

    ports: list[tuple[str, str, int]] = []
    for write in indices:
        ports.extend(((f"io_write_{write}_valid", "input", 1),
                      (f"io_write_{write}_bits_idx", "input", 8),
                      (f"io_write_{write}_bits_way_en", "input", 4)))
        for field, width in fields:
            ports.append((f"io_write_{write}_bits_{field}", "input", width))
    return ports


def coh_specs() -> tuple[tuple[str, str, int], ...]:
    """Return coherent metadata ports. / 返回一致性元数据端口。"""

    ports = [("clock", "input", 1), ("reset", "input", 1)]
    ports += read_ports((0, 1, 2, 3), 2, (("coh_state", 2),))
    ports += write_ports((0,), (("meta_coh_state", 2),))
    return tuple(ports)


def error_specs() -> tuple[tuple[str, str, int], ...]:
    """Return TileLink error metadata ports. / 返回 TileLink 错误元数据端口。"""

    ports = [("clock", "input", 1), ("reset", "input", 1)]
    ports += read_ports((0, 1, 2, 3), 1, (("tl_denied", 1), ("tl_corrupt", 1)))
    ports += write_ports((0,), (("error_tl_denied", 1), ("error_tl_corrupt", 1)))
    return tuple(ports)


def flag_specs() -> tuple[tuple[str, str, int], ...]:
    """Return flag metadata ports. / 返回标志元数据端口。"""

    ports = [("clock", "input", 1), ("reset", "input", 1)]
    ports += read_ports((3, 4), 1, (("", 1),))
    for write in range(4):
        ports.extend(((f"io_write_{write}_valid", "input", 1),
                      (f"io_write_{write}_bits_idx", "input", 8),
                      (f"io_write_{write}_bits_way_en", "input", 4)))
        if write == 3:
            ports.append(("io_write_3_bits_flag", "input", 1))
    return tuple(ports)


def source_specs() -> tuple[tuple[str, str, int], ...]:
    """Return prefetch-source metadata ports. / 返回预取来源元数据端口。"""

    ports = [("clock", "input", 1), ("reset", "input", 1)]
    ports += read_ports((0, 1, 2, 3, 4), 3, (("", 3),))
    for write in range(4):
        ports.extend(((f"io_write_{write}_valid", "input", 1),
                      (f"io_write_{write}_bits_idx", "input", 8),
                      (f"io_write_{write}_bits_way_en", "input", 4)))
        if write == 3:
            ports.append(("io_write_3_bits_source", "input", 3))
    return tuple(ports)


PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {
    "L1CohMetaArray": coh_specs(),
    "L1ErrorMetaArray": error_specs(),
    "L1FlagMetaArray": flag_specs(),
    "L1PrefetchSourceArray": source_specs(),
}

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

READ_INDICES = {
    "L1CohMetaArray": (0, 1, 2, 3), "L1ErrorMetaArray": (0, 1, 2, 3),
    "L1FlagMetaArray": (3, 4), "L1PrefetchSourceArray": (0, 1, 2, 3, 4),
}


# =============================================================================
# Implementation
# =============================================================================
class DcacheMetaArrayFamily(Elaboratable):
    """One four-way metadata array specialization. / 一个四路元数据阵列特化。"""

    def __init__(self, member: str = "L1CohMetaArray") -> None:
        """Declare exact locked ports. / 声明精确锁定端口。"""

        if member not in PORT_SPECS:
            raise ValueError(f"unsupported DCache metadata member: {member}")
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports: dict[str, Signal] = {
            name: Signal(width, name=name) for name, _direction, width in self.specs
        }
        self.clock = self.ports["clock"]
        self.reset = self.ports["reset"]

    # Return member field layouts. / 返回成员字段布局。
    def field_layout(self) -> tuple[tuple[str, int, str], ...]:
        """Map read suffix, width, and write suffix. / 映射读取后缀、位宽与写入后缀。"""

        if self.member == "L1CohMetaArray":
            return (("coh_state", 2, "meta_coh_state"),)
        if self.member == "L1ErrorMetaArray":
            return (("tl_denied", 1, "error_tl_denied"), ("tl_corrupt", 1, "error_tl_corrupt"))
        if self.member == "L1FlagMetaArray":
            return (("", 1, "flag"),)
        return (("", 3, "source"),)

    # Elaborate the four-way storage. / 展开四路存储。
    def elaborate(self, platform: Any) -> Module:
        """Implement registered reads and per-way writes. / 实现寄存读取及逐路写入。"""

        del platform
        module = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        module.domains += domain
        layouts = self.field_layout()
        memories: dict[str, list[Array]] = {}
        for read_suffix, width, _write_suffix in layouts:
            memories[read_suffix] = [
                Array(Signal(width, name=f"meta_{read_suffix or 'value'}_{way}_{index}", reset=0)
                      for index in range(256)) for way in range(4)
            ]

        for read in READ_INDICES[self.member]:
            address = Signal(8, name=f"meta_read_address_{read}")
            with cast(Any, module.If(self.ports[f"io_read_{read}_valid"])):
                module.d.sync += address.eq(self.ports[f"io_read_{read}_bits_idx"])
            for way in range(4):
                for read_suffix, _width, _write_suffix in layouts:
                    suffix = f"_{read_suffix}" if read_suffix else ""
                    module.d.comb += self.ports[f"io_resp_{read}_{way}{suffix}"].eq(
                        memories[read_suffix][way][address]
                    )

        write_indices = (0,) if self.member in {"L1CohMetaArray", "L1ErrorMetaArray"} else (0, 1, 2, 3)
        for write in write_indices:
            valid = self.ports[f"io_write_{write}_valid"]
            address = self.ports[f"io_write_{write}_bits_idx"]
            enables = self.ports[f"io_write_{write}_bits_way_en"]
            for way in range(4):
                with cast(Any, module.If(valid & cast(Any, enables[way]))):
                    for read_suffix, width, write_suffix in layouts:
                        value_name = f"io_write_{write}_bits_{write_suffix}"
                        value = self.ports[value_name] if value_name in self.ports else Signal(width, init=0)
                        module.d.sync += memories[read_suffix][way][address].eq(value)
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
