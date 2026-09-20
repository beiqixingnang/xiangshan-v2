"""Kunminghu V2 residual DatamoduleResultBuffer and RegionWays family.
昆明湖 V2 剩余 DatamoduleResultBuffer 与 RegionWays 聚合实现。
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, cast

from amaranth import Array, Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal, Value
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
COVERED_MODULES = ("DatamoduleResultBuffer", "RegionWays")
SOURCE_PATHS = (
    "upstream/src/main/scala/xiangshan/mem/sbuffer/DatamoduleResultBuffer.scala",
    "upstream/src/main/scala/xiangshan/frontend/ITTAGE.scala",
    "upstream/rocket-chip/src/main/scala/util/Replacement.scala",
)
LOCKED_PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {
    "DatamoduleResultBuffer": (
        ("clock", "input", 1), ("reset", "input", 1),
        ("io_enq_0_ready", "output", 1), ("io_enq_0_valid", "input", 1),
        ("io_enq_0_bits_addr", "input", 48), ("io_enq_0_bits_vaddr", "input", 50),
        ("io_enq_0_bits_data", "input", 128), ("io_enq_0_bits_mask", "input", 16),
        ("io_enq_0_bits_wline", "input", 1), ("io_enq_0_bits_sqPtr_value", "input", 6),
        ("io_enq_0_bits_vecValid", "input", 1), ("io_enq_0_bits_sqNeedDeq", "input", 1),
        ("io_enq_1_ready", "output", 1), ("io_enq_1_valid", "input", 1),
        ("io_enq_1_bits_addr", "input", 48), ("io_enq_1_bits_vaddr", "input", 50),
        ("io_enq_1_bits_data", "input", 128), ("io_enq_1_bits_mask", "input", 16),
        ("io_enq_1_bits_wline", "input", 1), ("io_enq_1_bits_sqPtr_value", "input", 6),
        ("io_enq_1_bits_vecValid", "input", 1),
        ("io_deq_0_ready", "input", 1), ("io_deq_0_valid", "output", 1),
        ("io_deq_0_bits_addr", "output", 48), ("io_deq_0_bits_vaddr", "output", 50),
        ("io_deq_0_bits_data", "output", 128), ("io_deq_0_bits_mask", "output", 16),
        ("io_deq_0_bits_wline", "output", 1), ("io_deq_0_bits_sqPtr_value", "output", 6),
        ("io_deq_0_bits_vecValid", "output", 1), ("io_deq_0_bits_sqNeedDeq", "output", 1),
        ("io_deq_1_ready", "input", 1), ("io_deq_1_valid", "output", 1),
        ("io_deq_1_bits_addr", "output", 48), ("io_deq_1_bits_vaddr", "output", 50),
        ("io_deq_1_bits_data", "output", 128), ("io_deq_1_bits_mask", "output", 16),
        ("io_deq_1_bits_wline", "output", 1), ("io_deq_1_bits_sqPtr_value", "output", 6),
        ("io_deq_1_bits_vecValid", "output", 1), ("io_deq_1_bits_sqNeedDeq", "output", 1),
    ),
    "RegionWays": (
        ("clock", "input", 1), ("reset", "input", 1),
        ("io_req_pointer_0", "input", 4), ("io_req_pointer_1", "input", 4),
        ("io_req_pointer_2", "input", 4), ("io_req_pointer_3", "input", 4),
        ("io_req_pointer_4", "input", 4),
        ("io_resp_hit_0", "output", 1), ("io_resp_hit_1", "output", 1),
        ("io_resp_hit_2", "output", 1), ("io_resp_hit_3", "output", 1),
        ("io_resp_hit_4", "output", 1),
        ("io_resp_region_0", "output", 30), ("io_resp_region_1", "output", 30),
        ("io_resp_region_2", "output", 30), ("io_resp_region_3", "output", 30),
        ("io_resp_region_4", "output", 30),
        ("io_update_region_0", "input", 30), ("io_update_region_1", "input", 30),
        ("io_update_hit_0", "output", 1), ("io_update_hit_1", "output", 1),
        ("io_update_pointer_0", "output", 4), ("io_update_pointer_1", "output", 4),
        ("io_write_valid", "input", 1), ("io_write_region", "input", 30),
        ("io_write_pointer", "output", 4),
    ),
}
PORT_SPECS = LOCKED_PORT_SPECS

__all__ = [
    "COVERED_MODULES", "SOURCE_PATHS", "LOCKED_PORT_SPECS", "PORT_SPECS",
    "FinalTwoFamily", "plru_next_int", "plru_replace_int", "build_verilog", "main",
]


# =============================================================================
# Configuration
# =============================================================================
PAYLOAD_FIELDS: tuple[tuple[str, int], ...] = (
    ("addr", 48), ("vaddr", 50), ("data", 128), ("mask", 16),
    ("wline", 1), ("sqPtr_value", 6), ("vecValid", 1), ("sqNeedDeq", 1),
)


def amaranth_if(module: Module, condition: Any) -> AbstractContextManager[None]:
    """Expose Amaranth conditional contexts to Pyright. / 向 Pyright 暴露 Amaranth 条件上下文。"""

    return cast(AbstractContextManager[None], module.If(condition))


def plru_replace_int(state: int, ways: int = 16) -> int:
    """Return the Rocket PseudoLRU replacement way. / 返回 Rocket PseudoLRU 替换路。"""

    if ways < 2 or ways & (ways - 1):
        raise ValueError("ways must be a power of two greater than one")
    if ways == 2:
        return state & 1
    half = ways // 2
    root = (state >> (ways - 2)) & 1
    subtree_mask = (1 << (half - 1)) - 1
    child_state = ((state >> (half - 1)) & subtree_mask) if root else (state & subtree_mask)
    return (root << (ways.bit_length() - 2)) | plru_replace_int(child_state, half)


def plru_next_int(state: int, touch: int, ways: int = 16) -> int:
    """Return the Rocket PseudoLRU state after one touch. / 返回一次访问后的 PseudoLRU 状态。"""

    if ways < 2 or ways & (ways - 1):
        raise ValueError("ways must be a power of two greater than one")
    if not 0 <= touch < ways:
        raise ValueError("touch way is outside the tree")
    if ways == 2:
        return 1 ^ (touch & 1)
    half = ways // 2
    lower_mask = (1 << (half - 1)) - 1
    right_state = state & lower_mask
    left_state = (state >> (half - 1)) & lower_mask
    touch_left = (touch >> (ways.bit_length() - 2)) == 0
    root = int(touch_left)
    if touch_left:
        right_state = plru_next_int(right_state, touch & (half - 1), half)
    else:
        left_state = plru_next_int(left_state, touch & (half - 1), half)
    return right_state | (left_state << (half - 1)) | (root << (ways - 2))


def plru_replace_value(state: Any, ways: int) -> Any:
    """Build the combinational PseudoLRU replacement expression. / 构造 PseudoLRU 替换组合表达式。"""

    if ways == 2:
        return state[0]
    half = ways // 2
    root = state[ways - 2]
    right_state = state[: half - 1]
    left_state = state[half - 1 : ways - 2]
    child = Mux(root, plru_replace_value(left_state, half), plru_replace_value(right_state, half))
    return Cat(child, root)


def plru_next_value(state: Any, touch: Any, ways: int) -> Any:
    """Build the combinational PseudoLRU next-state expression. / 构造 PseudoLRU 下一状态表达式。"""

    if ways == 2:
        return ~touch[0]
    half = ways // 2
    address_bits = ways.bit_length() - 1
    root = ~touch[address_bits - 1]
    right_state = state[: half - 1]
    left_state = state[half - 1 : ways - 2]
    child_touch = touch[: address_bits - 1]
    next_left = Mux(root, left_state, plru_next_value(left_state, child_touch, half))
    next_right = Mux(root, plru_next_value(right_state, child_touch, half), right_state)
    return Cat(next_right, next_left, root)


# =============================================================================
# Implementation
# =============================================================================
class FinalTwoFamily(Elaboratable):
    """Exact locked behavior for one selected family member. / 所选 family 成员的精确锁定行为。"""

    def __init__(self, member: str = COVERED_MODULES[0]) -> None:
        if member not in PORT_SPECS:
            raise ValueError(member)
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports = {name: Signal(width, name=name) for name, _direction, width in self.specs}

    def elaborate(self, platform: Any) -> Module:
        """Elaborate the selected V2 member. / 展开选定的 V2 成员。"""

        del platform
        if self.member == "DatamoduleResultBuffer":
            return self.elaborate_result_buffer()
        return self.elaborate_region_ways()

    def elaborate_result_buffer(self) -> Module:
        """Elaborate the exact two-entry circular result buffer. / 展开精确双项循环结果缓冲。"""

        module = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.ports["clock"]
        domain.rst = self.ports["reset"]
        module.domains += domain

        data: list[dict[str, Signal]] = []
        for entry in range(2):
            data.append({
                field: Signal(width, name=f"data_{entry}_{field}", reset_less=True)
                for field, width in PAYLOAD_FIELDS
            })
        valids = [Signal(name=f"valids_{entry}") for entry in range(2)]
        enq_flag = Signal(name="enq_flag")
        deq_flag = Signal(name="deq_flag")

        deq_indices = (deq_flag, ~deq_flag)
        enq_indices = (enq_flag, ~enq_flag)
        deq_valid_0 = Mux(deq_flag, valids[1], valids[0])
        deq_valid_1 = Mux(~deq_flag, valids[1], valids[0]) & deq_valid_0
        deq_fire = (
            deq_valid_0 & self.ports["io_deq_0_ready"],
            deq_valid_1 & self.ports["io_deq_1_ready"],
        )

        allow: list[Value] = []
        for entry in range(2):
            drained = (deq_fire[0] & (deq_indices[0] == entry)) | (
                deq_fire[1] & (deq_indices[1] == entry)
            )
            allow.append(~valids[entry] | drained)
        enq_ready_0 = Mux(enq_flag, allow[1], allow[0])
        enq_ready_1 = Mux(~enq_flag, allow[1], allow[0]) & enq_ready_0
        enq_fire = (
            enq_ready_0 & self.ports["io_enq_0_valid"],
            enq_ready_1 & self.ports["io_enq_1_valid"],
        )

        module.d.comb += [
            self.ports["io_enq_0_ready"].eq(enq_ready_0),
            self.ports["io_enq_1_ready"].eq(enq_ready_1),
            self.ports["io_deq_0_valid"].eq(deq_valid_0),
            self.ports["io_deq_1_valid"].eq(deq_valid_1),
        ]
        for lane, index in enumerate(deq_indices):
            for field, _width in PAYLOAD_FIELDS:
                module.d.comb += self.ports[f"io_deq_{lane}_bits_{field}"].eq(
                    Mux(index, data[1][field], data[0][field])
                )

        for entry in range(2):
            enq_0_here = enq_fire[0] & (enq_indices[0] == entry)
            enq_1_here = enq_fire[1] & (enq_indices[1] == entry)
            deq_here = (deq_fire[0] & (deq_indices[0] == entry)) | (
                deq_fire[1] & (deq_indices[1] == entry)
            )
            module.d.sync += valids[entry].eq(
                Mux(enq_0_here | enq_1_here, 1, Mux(deq_here, 0, valids[entry]))
            )
            with amaranth_if(module, enq_1_here):
                for field, _width in PAYLOAD_FIELDS:
                    value: Any = (
                        1 if field == "sqNeedDeq"
                        else self.ports[f"io_enq_1_bits_{field}"]
                    )
                    module.d.sync += data[entry][field].eq(value)
            with amaranth_if(module, enq_0_here):
                for field, _width in PAYLOAD_FIELDS:
                    module.d.sync += data[entry][field].eq(self.ports[f"io_enq_0_bits_{field}"])

        with amaranth_if(module, enq_fire[0] & ~enq_fire[1]):
            module.d.sync += enq_flag.eq(~enq_flag)
        with amaranth_if(module, deq_fire[0] & ~deq_fire[1]):
            module.d.sync += deq_flag.eq(~deq_flag)
        return module

    def elaborate_region_ways(self) -> Module:
        """Elaborate the exact 16-entry region table and PLRU. / 展开精确 16 项区域表和 PLRU。"""

        module = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.ports["clock"]
        domain.rst = self.ports["reset"]
        module.domains += domain

        region_valid = [Signal(name=f"regions_{way}_valid") for way in range(16)]
        region_data = [Signal(30, name=f"regions_{way}_region") for way in range(16)]
        state_reg = Signal(15, name="state_reg")
        valid_vector: Any = Cat(*region_valid)
        all_valid = valid_vector.all()

        write_hits = [
            region_valid[way] & (region_data[way] == self.ports["io_write_region"])
            for way in range(16)
        ]
        write_hit_vector: Any = Cat(*write_hits)
        write_hit = write_hit_vector.any()
        write_hit_pointer: Value = Const(0, 4)
        for way in range(16):
            write_hit_pointer = write_hit_pointer | Mux(write_hits[way], Const(way, 4), Const(0, 4))

        invalid_pointer: Value = Const(0, 4)
        for way in reversed(range(16)):
            invalid_pointer = Mux(~region_valid[way], Const(way, 4), invalid_pointer)
        replacement = plru_replace_value(state_reg, 16)
        write_pointer = Mux(write_hit, write_hit_pointer, Mux(~all_valid, invalid_pointer, replacement))
        module.d.comb += self.ports["io_write_pointer"].eq(write_pointer)

        region_array = Array(region_data)
        valid_array = Array(region_valid)
        for port in range(5):
            pointer = self.ports[f"io_req_pointer_{port}"]
            module.d.comb += [
                self.ports[f"io_resp_hit_{port}"].eq(valid_array[pointer]),
                self.ports[f"io_resp_region_{port}"].eq(region_array[pointer]),
            ]

        for port in range(2):
            update_region = self.ports[f"io_update_region_{port}"]
            update_hits = [
                region_valid[way] & (region_data[way] == update_region)
                for way in range(16)
            ]
            hit_vector: Any = Cat(*update_hits)
            hit_pointer: Value = Const(0, 4)
            for way in range(16):
                hit_pointer = hit_pointer | Mux(update_hits[way], Const(way, 4), Const(0, 4))
            bypass = self.ports["io_write_valid"] & (update_region == self.ports["io_write_region"])
            module.d.comb += [
                self.ports[f"io_update_hit_{port}"].eq(hit_vector.any() | bypass),
                self.ports[f"io_update_pointer_{port}"].eq(Mux(bypass, write_pointer, hit_pointer)),
            ]

        for way in range(16):
            selected = self.ports["io_write_valid"] & (write_pointer == way)
            with amaranth_if(module, selected):
                module.d.sync += [
                    region_valid[way].eq(1),
                    region_data[way].eq(self.ports["io_write_region"]),
                ]
        with amaranth_if(module, self.ports["io_write_valid"]):
            module.d.sync += state_reg.eq(plru_next_value(state_reg, write_pointer, 16))
        return module


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: Any = None, injected_dependencies: Any = None) -> str:
    """Emit one exact-name locked family member. / 输出一个精确同名的锁定 family 成员。"""

    del injected_dependencies
    member = COVERED_MODULES[0]
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = FinalTwoFamily(member)
    return verilog.convert(
        top, name=member,
        ports=[top.ports[name] for name, _direction, _width in top.specs], emit_src=False,
    )


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the default exact family member. / 打印默认精确 family 成员。"""

    print(build_verilog({"module": COVERED_MODULES[0]}, {}))


if __name__ == "__main__":
    main()
