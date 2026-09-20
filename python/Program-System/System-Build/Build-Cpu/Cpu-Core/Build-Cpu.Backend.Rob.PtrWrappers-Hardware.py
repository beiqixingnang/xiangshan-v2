"""UHSC V2 reorder-buffer circular-pointer wrapper family.
昆明湖 V2 重排序缓冲区循环指针封装 family。

The locked Kunminghu V2 configuration has a 160-entry ROB, six rename lanes,
and eight commit lanes.  This catalog exports the two real Chisel/FIRRTL module
boundaries independently; it deliberately does not invent a combined parent.
"""

from __future__ import annotations

from typing import Any, cast

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = ["COVERED_MODULES", "RobPtrWrapper", "build_verilog", "main"]

COVERED_MODULES = ("RobEnqPtrWrapper", "NewRobDeqPtrWrapper")
SOURCE_PATHS = (
    "upstream/src/main/scala/xiangshan/backend/rob/RobEnqPtrWrapper.scala",
    "upstream/src/main/scala/xiangshan/backend/rob/RobDeqPtrWrapper.scala",
    "upstream/src/main/scala/xiangshan/backend/rob/RobBundles.scala",
    "upstream/utility/src/main/scala/utility/CircularQueuePtr.scala",
    "upstream/utility/src/main/scala/utility/PriorityMuxDefault.scala",
)

PortSpec = tuple[str, str, int]

LOCKED_PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    "RobEnqPtrWrapper": (
        ("clock", "input", 1),
        ("reset", "input", 1),
        ("io_redirect_valid", "input", 1),
        ("io_redirect_bits_robIdx_flag", "input", 1),
        ("io_redirect_bits_robIdx_value", "input", 8),
        ("io_redirect_bits_level", "input", 1),
        ("io_allowEnqueue", "input", 1),
        ("io_hasBlockBackward", "input", 1),
        *((f"io_enq_{index}", "input", 1) for index in range(6)),
        ("io_out_0_flag", "output", 1),
        *((f"io_out_{index}_value", "output", 8) for index in range(6)),
    ),
    "NewRobDeqPtrWrapper": (
        ("clock", "input", 1),
        ("reset", "input", 1),
        ("io_state", "input", 2),
        *((f"io_deq_v_{index}", "input", 1) for index in range(8)),
        *((f"io_deq_w_{index}", "input", 1) for index in range(8)),
        *((f"io_hasCommitted_{index}", "input", 1) for index in range(8)),
        ("io_exception_state_valid", "input", 1),
        ("io_exception_state_bits_robIdx_flag", "input", 1),
        ("io_exception_state_bits_robIdx_value", "input", 8),
        ("io_exception_state_bits_hasException", "input", 1),
        ("io_exception_state_bits_replayInst", "input", 1),
        ("io_exception_state_bits_singleStep", "input", 1),
        ("io_exception_state_bits_trigger", "input", 4),
        ("io_intrBitSetReg", "input", 1),
        ("io_allowOnlyOneCommit", "input", 1),
        ("io_hasNoSpecExec", "input", 1),
        ("io_interrupt_safe", "input", 1),
        ("io_blockCommit", "input", 1),
        *(
            item
            for index in range(8)
            for item in (
                (f"io_out_{index}_flag", "output", 1),
                (f"io_out_{index}_value", "output", 8),
            )
        ),
        ("io_next_out_0_flag", "output", 1),
        ("io_next_out_0_value", "output", 8),
    ),
}
PORT_SPECS = LOCKED_PORT_SPECS


# =============================================================================
# Circular-pointer helpers
# =============================================================================
ROB_SIZE = 160


def _wide(value: Any) -> Any:
    """Zero-extend an eight-bit ROB value for non-power-of-two arithmetic."""

    return Cat(value, Const(0, 1))


def _circular_add(value: Any, flag: Any, amount: Any) -> tuple[Any, Any]:
    """Add once in the locked 160-entry circular domain."""

    total = cast(Any, _wide(value)) + amount
    reverse = total >= ROB_SIZE
    wrapped = Mux(reverse, total - ROB_SIZE, total)
    return wrapped[:8], flag ^ reverse


def _first_priority(conditions: list[Any], choices: list[Any], default: Any) -> Any:
    """Return Chisel PriorityMuxDefault semantics (lowest index wins)."""

    selected = default
    for condition, choice in reversed(list(zip(conditions, choices, strict=True))):
        selected = Mux(condition, choice, selected)
    return selected


# =============================================================================
# Implementation
# =============================================================================
class RobPtrWrapper(Elaboratable):
    """One exact-name locked V2 ROB pointer-wrapper member."""

    def __init__(self, member: str = "RobEnqPtrWrapper") -> None:
        """Declare the exact flattened ABI for ``member``."""

        if member not in PORT_SPECS:
            raise ValueError(member)
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports = {
            name: Signal(width, name=name)
            for name, _direction, width in self.specs
        }

    def _domain(self, module: Module) -> None:
        """Bind the emitted clock/reset ports to Chisel's async-reset domain."""

        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.ports["clock"]
        domain.rst = self.ports["reset"]
        module.domains += domain

    def _enqueue(self, module: Module) -> None:
        """Implement six-lane redirect and PopCount-based enqueue movement."""

        p = self.ports
        values = [Signal(8, reset=index, name=f"enqPtrVec_{index}_value")
                  for index in range(6)]
        flag = Signal(reset=0, name="enqPtrVec_0_flag")

        dispatch: Any = Const(0, 4)
        for index in range(6):
            dispatch = cast(Any, dispatch) + p[f"io_enq_{index}"]
        can_accept = p["io_allowEnqueue"] & ~p["io_hasBlockBackward"]
        advance = Mux(can_accept, dispatch, 0)
        redirect_offset = Mux(p["io_redirect_bits_level"], 0, 1)

        for index, value in enumerate(values):
            regular_value, regular_flag = _circular_add(value, flag, advance)
            redirect_value, redirect_flag = _circular_add(
                p["io_redirect_bits_robIdx_value"],
                p["io_redirect_bits_robIdx_flag"],
                cast(Any, redirect_offset) + index,
            )
            next_value = Mux(p["io_redirect_valid"], redirect_value, regular_value)
            module.d.sync += value.eq(next_value)
            if index == 0:
                module.d.sync += flag.eq(
                    Mux(p["io_redirect_valid"], redirect_flag, regular_flag)
                )

        module.d.comb += p["io_out_0_flag"].eq(flag)
        for index, value in enumerate(values):
            module.d.comb += p[f"io_out_{index}_value"].eq(value)

    def _dequeue(self, module: Module) -> None:
        """Implement the eight-lane V2 commit-pointer selection and gating."""

        p = self.ports
        values = [Signal(8, reset=index, name=f"deqPtrVec_{index}_value")
                  for index in range(8)]
        flags = [Signal(reset=0, name=f"deqPtrVec_{index}_flag")
                 for index in range(8)]

        position = values[0][:3]
        can_commit = [
            (p[f"io_deq_v_{index}"] & p[f"io_deq_w_{index}"])
            | p[f"io_hasCommitted_{index}"]
            for index in range(8)
        ]
        can_commit_vector = Cat(*can_commit)
        deq_v_vector = Cat(*(p[f"io_deq_v_{index}"] for index in range(8)))
        deq_w_vector = Cat(*(p[f"io_deq_w_{index}"] for index in range(8)))
        can_at_position = cast(Any, can_commit_vector).bit_select(position, 1)
        deq_v_at_position = cast(Any, deq_v_vector).bit_select(position, 1)
        deq_w_at_position = cast(Any, deq_w_vector).bit_select(position, 1)

        normal_conditions: list[Any] = [~value for value in can_commit]
        normal_conditions.append(Const(1))
        one_conditions: list[Any] = [Const(0)]
        one_conditions.extend(
            cast(Any, position == index) & can_at_position for index in range(8)
        )
        conditions = [
            Mux(p["io_allowOnlyOneCommit"], one, normal)
            for one, normal in zip(one_conditions, normal_conditions, strict=True)
        ]

        line_head = Cat(Const(0, 3), values[0][3:8], Const(0, 1))
        candidates = [
            _circular_add(line_head[:8], flags[0], Const(offset, 5))
            for offset in range(16)
        ]
        selected_values: list[Any] = []
        selected_flags: list[Any] = []
        for lane in range(8):
            selected_values.append(_first_priority(
                conditions,
                [candidates[lane + index][0] for index in range(9)],
                values[lane],
            ))
            selected_flags.append(_first_priority(
                conditions,
                [candidates[lane + index][1] for index in range(9)],
                flags[lane],
            ))

        not_commit = (
            p["io_exception_state_bits_hasException"]
            | p["io_exception_state_bits_replayInst"]
            | p["io_exception_state_bits_singleStep"]
            | (p["io_exception_state_bits_trigger"] == 1)
        )
        pointer_matches = (
            (p["io_exception_state_bits_robIdx_flag"] == flags[0])
            & (p["io_exception_state_bits_robIdx_value"] == values[0])
        )
        interrupt_enable = (
            p["io_intrBitSetReg"]
            & ~p["io_hasNoSpecExec"]
            & p["io_interrupt_safe"]
        )
        exception_enable = (
            deq_w_at_position
            & p["io_exception_state_valid"]
            & not_commit
            & pointer_matches
        )
        state_idle = p["io_state"] == 0
        redirect = (
            state_idle
            & deq_v_at_position
            & (interrupt_enable | exception_enable)
        )
        update = state_idle & ~redirect & ~p["io_blockCommit"]

        for index in range(8):
            module.d.sync += [
                values[index].eq(Mux(update, selected_values[index], values[index])),
                flags[index].eq(Mux(update, selected_flags[index], flags[index])),
            ]
            module.d.comb += [
                p[f"io_out_{index}_flag"].eq(flags[index]),
                p[f"io_out_{index}_value"].eq(values[index]),
            ]
        module.d.comb += [
            p["io_next_out_0_flag"].eq(Mux(update, selected_flags[0], flags[0])),
            p["io_next_out_0_value"].eq(Mux(update, selected_values[0], values[0])),
        ]

    def elaborate(self, platform: Any) -> Module:
        """Elaborate the selected exact-name member."""

        del platform
        module = Module()
        self._domain(module)
        if self.member == "RobEnqPtrWrapper":
            self._enqueue(module)
        else:
            self._dequeue(module)
        return module


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: Any = None,
                  injected_dependencies: Any = None) -> str:
    """Export one deterministic, exact-name locked family member."""

    del injected_dependencies
    member = "RobEnqPtrWrapper"
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = RobPtrWrapper(member)
    return verilog.convert(
        top,
        name=member,
        ports=[top.ports[name] for name, _direction, _width in top.specs],
        emit_src=False,
    )


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the default enqueue-wrapper RTL."""

    print(build_verilog({"module": "RobEnqPtrWrapper"}, {}))


if __name__ == "__main__":
    main()
