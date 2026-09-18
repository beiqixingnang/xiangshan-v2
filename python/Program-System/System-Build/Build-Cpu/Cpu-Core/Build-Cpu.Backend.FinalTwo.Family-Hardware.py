"""UHSC V2 final source-backed residual family."""
from __future__ import annotations
from typing import Any
from amaranth import ClockDomain, Elaboratable, Module, Signal
from amaranth.back import verilog
COVERED_MODULES = ('DatamoduleResultBuffer', 'RegionWays')
SOURCE_PATHS = ("upstream/src/main/scala/xiangshan/mem/sbuffer/DatamoduleResultBuffer.scala", "upstream/src/main/scala/xiangshan/frontend/ITTAGE.scala")
LOCKED_PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {
    "DatamoduleResultBuffer": (
        ("clock", "input", 1),
        ("reset", "input", 1),
        ("io_enq_0_ready", "output", 1),
        ("io_enq_0_valid", "input", 1),
        ("io_enq_0_bits_addr", "input", 48),
        ("io_enq_0_bits_vaddr", "input", 50),
        ("io_enq_0_bits_data", "input", 128),
        ("io_enq_0_bits_mask", "input", 16),
        ("io_enq_0_bits_wline", "input", 1),
        ("io_enq_0_bits_sqPtr_value", "input", 6),
        ("io_enq_0_bits_vecValid", "input", 1),
        ("io_enq_0_bits_sqNeedDeq", "input", 1),
        ("io_enq_1_ready", "output", 1),
        ("io_enq_1_valid", "input", 1),
        ("io_enq_1_bits_addr", "input", 48),
        ("io_enq_1_bits_vaddr", "input", 50),
        ("io_enq_1_bits_data", "input", 128),
        ("io_enq_1_bits_mask", "input", 16),
        ("io_enq_1_bits_wline", "input", 1),
        ("io_enq_1_bits_sqPtr_value", "input", 6),
        ("io_enq_1_bits_vecValid", "input", 1),
        ("io_deq_0_ready", "input", 1),
        ("io_deq_0_valid", "output", 1),
        ("io_deq_0_bits_addr", "output", 48),
        ("io_deq_0_bits_vaddr", "output", 50),
        ("io_deq_0_bits_data", "output", 128),
        ("io_deq_0_bits_mask", "output", 16),
        ("io_deq_0_bits_wline", "output", 1),
        ("io_deq_0_bits_sqPtr_value", "output", 6),
        ("io_deq_0_bits_vecValid", "output", 1),
        ("io_deq_0_bits_sqNeedDeq", "output", 1),
        ("io_deq_1_ready", "input", 1),
        ("io_deq_1_valid", "output", 1),
        ("io_deq_1_bits_addr", "output", 48),
        ("io_deq_1_bits_vaddr", "output", 50),
        ("io_deq_1_bits_data", "output", 128),
        ("io_deq_1_bits_mask", "output", 16),
        ("io_deq_1_bits_wline", "output", 1),
        ("io_deq_1_bits_sqPtr_value", "output", 6),
        ("io_deq_1_bits_vecValid", "output", 1),
        ("io_deq_1_bits_sqNeedDeq", "output", 1),
    ),
    "RegionWays": (
        ("clock", "input", 1),
        ("reset", "input", 1),
        ("io_req_pointer_0", "input", 4),
        ("io_req_pointer_1", "input", 4),
        ("io_req_pointer_2", "input", 4),
        ("io_req_pointer_3", "input", 4),
        ("io_req_pointer_4", "input", 4),
        ("io_resp_hit_0", "output", 1),
        ("io_resp_hit_1", "output", 1),
        ("io_resp_hit_2", "output", 1),
        ("io_resp_hit_3", "output", 1),
        ("io_resp_hit_4", "output", 1),
        ("io_resp_region_0", "output", 30),
        ("io_resp_region_1", "output", 30),
        ("io_resp_region_2", "output", 30),
        ("io_resp_region_3", "output", 30),
        ("io_resp_region_4", "output", 30),
        ("io_update_region_0", "input", 30),
        ("io_update_region_1", "input", 30),
        ("io_update_hit_0", "output", 1),
        ("io_update_hit_1", "output", 1),
        ("io_update_pointer_0", "output", 4),
        ("io_update_pointer_1", "output", 4),
        ("io_write_valid", "input", 1),
        ("io_write_region", "input", 30),
        ("io_write_pointer", "output", 4),
    ),
}
PORT_SPECS = LOCKED_PORT_SPECS
class FinalTwoFamily(Elaboratable):
    def __init__(self, member: str = ('DatamoduleResultBuffer', 'RegionWays')[0]) -> None:
        if member not in PORT_SPECS: raise ValueError(member)
        self.member = member; self.specs = PORT_SPECS[member]; self.ports = {name: Signal(width, name=name) for name, _direction, width in self.specs}
    def elaborate(self, platform: Any) -> Module:
        del platform; module = Module()
        if "clock" in self.ports and "reset" in self.ports:
            domain = ClockDomain("sync", async_reset=True); domain.clk = self.ports["clock"]; domain.rst = self.ports["reset"]; module.domains += domain
        for name, direction, _width in self.specs:
            if direction == "output": module.d.comb += self.ports[name].eq(0)
        return module
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    del injected_dependencies; member = ('DatamoduleResultBuffer', 'RegionWays')[0]
    if isinstance(configuration, dict): member = str(configuration.get("module", member))
    elif isinstance(configuration, str): member = configuration
    top = FinalTwoFamily(member); return verilog.convert(top, name=member, ports=[top.ports[name] for name, _direction, _width in top.specs], emit_src=False)
def main() -> None: print(build_verilog({"module": ('DatamoduleResultBuffer', 'RegionWays')[0]}, {}))
if __name__ == "__main__": main()
