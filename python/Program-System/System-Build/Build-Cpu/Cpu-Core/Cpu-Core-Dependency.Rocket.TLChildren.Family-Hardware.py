"""Source-backed Rocket TileLink child family for TOP-L2TOP-TL2TL-003.

The selected children keep their exact frozen interfaces. TLBuffers implement
real FIFO channels; TLXbar_8 implements address/source routing and beat-locked
arbitration; TLXbar_9 implements coherent four-client arbitration and source
demultiplexing; BusErrorUnit implements the MMIO and sticky error state.
TLXbar_7 implements striped manager routing. Complete parent closure is pending.
"""
from __future__ import annotations
import base64
import json
import re
import zlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, NamedTuple, Sequence, cast
from amaranth import (Array, Cat, ClockDomain, ClockSignal, Const, Elaboratable, Memory, Module,
                      Mux,
                      ResetSignal, Signal)
from amaranth.back import verilog

# Module Contract / 模块契约
__all__ = [
    'COVERED_MODULES',
    'PortSpec',
    'FamilySpec',
    'PORT_SPECS',
    'family_spec',
    'TLChildFamily',
    'RocketTLChildrenFamily',
    'relay_observation',
    'tlbuffer_model',
    'merge_source_ids',
    'bus_error_observation',
    'build_verilog',
    'main',
]

COVERED_MODULES = (
    "TLXbar_7", "TLXbar_8", "TLXbar_9", "TLBuffer_27", "TLBuffer_20",
    "TLBuffer_29", "TLBuffer_22", "TLBuffer_16", "TLBuffer_2",
    "TLClientsMerger_1", "BusErrorUnit",
)

# Configuration / 配置
class PortSpec(NamedTuple):
    name: str
    direction: str
    width: int

_LOCKED_PORT_BLOB = "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"
_LOCKED_PORTS: dict[str, list[list[Any]]] = json.loads(
    zlib.decompress(base64.b64decode(_LOCKED_PORT_BLOB)).decode("utf-8")
)
PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    module: tuple(PortSpec(str(name), str(direction), int(width))
                  for name, direction, width in rows)
    for module, rows in _LOCKED_PORTS.items()
}

# Implementation / 实现
@dataclass(frozen=True)
class FamilySpec:
    module: str

    # Validate one selected source member / 校验一个选定的源成员。
    def __post_init__(self) -> None:
        if self.module not in PORT_SPECS:
            raise ValueError(f"unknown TL child: {self.module}")
    @property
    # Return the exact frozen port tuple / 返回精确冻结端口元组。
    def ports(self) -> tuple[PortSpec, ...]:
        return PORT_SPECS[self.module]
    @property
    # Return the frozen port count / 返回冻结端口数量。
    def port_count(self) -> int:
        return len(self.ports)
    @property
    # Return the frozen aggregate bit count / 返回冻结聚合位宽。
    def port_bits(self) -> int:
        return sum(port.width for port in self.ports)

    # Return one named port width / 返回指定端口位宽。
    def width(self, name: str) -> int:
        for port in self.ports:
            if port.name == name:
                return port.width
        raise KeyError(name)

    # Test one named port presence / 判断指定端口是否存在。
    def has(self, name: str) -> bool:
        return any(port.name == name for port in self.ports)

# Resolve one exact family specification / 解析一个精确 family 规格。
def family_spec(module: str) -> FamilySpec:
    return FamilySpec(module)

# Normalize generated auto channel names / 规范化生成的 auto 通道名称。
def _tail(name: str) -> str:
    return re.sub(r"^auto_(?:in|out)(?:_[0-9]+)?_", "", name)


def _tlxbar8_or(values: Sequence[Any]) -> Any:
    """Reduce one non-empty sequence with the locked one-hot OR mux form."""

    if not values:
        raise ValueError("TLXbar_8 reductions must contain at least one value")
    result = values[0]
    for value in values[1:]:
        result = result | value
    return result


TLXBAR8_MANAGER2_ADDRESS_MASKS = (
    (0xffffe0000000, 0x000000000000),
    (0xfffff0000000, 0x000020000000),
    (0xffffff000000, 0x000030000000),
    (0xfffffff00000, 0x000031000000),
    (0xfffffffd8000, 0x000031100000),
    (0xfffffffc0000, 0x000031140000),
    (0xfffffff80000, 0x000031180000),
    (0xffffffe00000, 0x000031200000),
    (0xffffffc00000, 0x000031400000),
    (0xffffff800000, 0x000031800000),
    (0xfffff6000000, 0x000032000000),
    (0xfffff4000000, 0x000034000000),
    (0xffffffff0000, 0x000038000000),
    (0xfffffffff000, 0x000038011000),
    (0xffffffffe000, 0x000038012000),
    (0xffffffffc000, 0x000038014000),
    (0xffffffff8000, 0x000038018000),
    (0xffffffffe000, 0x000038020000),
    (0xffffffffff00, 0x000038022100),
    (0xfffffffffe00, 0x000038022200),
    (0xfffffffffc00, 0x000038022400),
    (0xfffffffff800, 0x000038022800),
    (0xfffffffff000, 0x000038023000),
    (0xffffffffc000, 0x000038024000),
    (0xffffffff8000, 0x000038028000),
    (0xffffffff0000, 0x000038030000),
    (0xfffffffc0000, 0x000038040000),
    (0xfffffff80000, 0x000038080000),
    (0xfffffff00000, 0x000038100000),
    (0xffffffe00000, 0x000038200000),
    (0xffffffc00000, 0x000038400000),
    (0xffffff800000, 0x000038800000),
    (0xffffff000000, 0x000039000000),)

def _tlxbar8_route(address: Any) -> tuple[Any, Any, Any]:
    """Decode the three locked TLXbar_8 manager address sets."""

    # These are the exact address-set unions in requestAIO_0_0 / _0_1 of the
    # locked module: [0x38010000, 0x38011000) and [0x38022000, 0x38022100).
    route_0 = address[12:48] == 0x38010
    route_1 = address[8:48] == 0x380220
    route_2: Any = address[30:48] != 0
    for mask, value in TLXBAR8_MANAGER2_ADDRESS_MASKS:
        route_2 = route_2 | ((address & Const(mask, 48)) == Const(value, 48))
    return route_0, route_1, route_2


def _tlxbar8_round_robin_readys(valids: Sequence[Any], mask: Any) -> list[Any]:
    """Match Rocket ``TLArbiter.roundRobin`` including idle ready behavior."""

    count = len(valids)
    # Rocket's ``Cat(valids.reverse)`` puts source 0 in the low bit; Amaranth
    # Cat arguments are already ordered low-to-high for this vector.
    valid_reversed = Cat(*valids)
    filtered = valid_reversed & ~mask
    policy_filter = Cat(valid_reversed, filtered)
    suffix: list[Any] = [Const(0, 1) for _ in range(2 * count + 1)]
    for index in reversed(range(2 * count)):
        suffix[index] = suffix[index + 1] | policy_filter[index]
    right_or = Cat(*suffix[:-1])
    unready = cast(Any, cast(Any, right_or) >> 1) | cast(Any, Cat(Const(0, count), mask))
    ready_reversed = ~(cast(Any, unready[count:]) & cast(Any, unready[:count]))
    return [ready_reversed[index] for index in range(count)]


def _tlxbar8_left_or(value: Any, width: int) -> list[Any]:
    """Return Rocket util.leftOR(value): low bits propagate toward high bits."""

    prefix: list[Any] = []
    accumulated: Any = Const(0, 1)
    for index in range(width):
        accumulated = accumulated | value[index]
        prefix.append(accumulated)
    return prefix


def _tlxbar8_beats_left(size: Any) -> Any:
    """Match ``~((13'h3f << size)[5:3])`` from Rocket's numBeats1 path."""

    shifted = Const(0x3F, 13) << size
    return ~shifted[3:6]


def _elaborate_tlxbar8(family: Any, module: Module) -> Module:
    """Elaborate exact A/D routing and five Rocket arbiters into ``module``.

    The caller invokes this from ``TLChildFamily.elaborate`` only for member
    ``TLXbar_8``. The generated candidate has three two-input A arbiters and
    two three-input D arbiters, with 22 state registers in the signal layout
    above (39 state bits total).
    """

    ports = family.ports
    domain = ClockDomain("sync", async_reset=True)
    domain.clk = ports["clock"]
    domain.rst = ports["reset"]
    module.domains += domain

    # Bind each generated Rocket arbiter directly into the parent module so
    # the state identifiers remain beatsLeft[_N], readys_mask[_N], state_*.

    def add_arbiter(
        index: int,
        valids: Sequence[Any],
        sink_ready: Any,
        sizes: Sequence[Any],
        data_beats: Sequence[Any],
    ) -> dict[str, Any]:
        suffix = "" if index == 0 else f"_{index}"
        beat_count = Signal(3, name=f"beatsLeft{suffix}")
        mask = Signal(
            len(valids),
            init=(1 << len(valids)) - 1,
            name=f"readys_mask{suffix}",
        )
        if index == 0:
            state_names = ("state_0", "state_1")
        else:
            state_names = tuple(f"state_{index}_{slot}" for slot in range(len(valids)))
        states = [Signal(name=name) for name in state_names]

        idle = Signal(name=f"idle{suffix}")
        readys = [Signal(name=f"arb{index}_ready_{slot}") for slot in range(len(valids))]
        winners = [Signal(name=f"arb{index}_winner_{slot}") for slot in range(len(valids))]
        mux_state = [Signal(name=f"arb{index}_mux_{slot}") for slot in range(len(valids))]
        allowed = [Signal(name=f"arb{index}_allowed_{slot}") for slot in range(len(valids))]
        module.d.comb += idle.eq(beat_count == 0)
        ready_expressions = _tlxbar8_round_robin_readys(valids, mask)
        for slot, (ready, winner, mux, permit) in enumerate(zip(readys, winners, mux_state, allowed)):
            module.d.comb += [ready.eq(ready_expressions[slot]),
                              winner.eq(ready & valids[slot]),
                              mux.eq(Mux(idle, winner, states[slot])),
                              permit.eq(Mux(idle, ready, states[slot]))]
        any_valid = _tlxbar8_or(valids)
        locked_valid = _tlxbar8_or(
            [state & valid for state, valid in zip(states, valids)]
        )
        output_valid = Mux(idle, any_valid, locked_valid)
        latch = idle & sink_ready
        fire = sink_ready & output_valid

        selected_bits = Cat(*(winner & valid for winner, valid in zip(readys, valids)))
        prefix = _tlxbar8_left_or(selected_bits, len(valids))
        next_mask = cast(Any, Cat(
            *(prefix[bit - 1] if bit else Const(0, 1) for bit in range(len(valids)))
        )) | cast(Any, Cat(*prefix))

        init_beats = _tlxbar8_or(
            [Mux(winner & has_data, _tlxbar8_beats_left(size), 0)
             for winner, has_data, size in zip(winners, data_beats, sizes)]
        )
        with cast(Any, module.If(latch & any_valid)):
            module.d.sync += mask.eq(next_mask)
        module.d.sync += [
            beat_count.eq(Mux(latch, init_beats, beat_count - fire)),
            *(state.eq(selected) for state, selected in zip(states, mux_state)),
        ]

        result = {
            "idle": idle,
            "valids": tuple(valids),
            "readys": tuple(readys),
            "winners": tuple(winners),
            "mux_state": tuple(mux_state),
            "allowed": tuple(allowed),
            "valid": output_valid,
        }
        return result

    # A-channel fanout: each input source is decoded against the exact same
    # three manager regions; each manager independently arbitrates two inputs.
    input_routes = [[Signal(name=f"requestAIO_{client}_{manager}") for manager in range(3)]
                    for client in range(2)]
    for client in range(2):
        expressions = _tlxbar8_route(ports[f"auto_in_{client}_a_bits_address"])
        for route, expression in zip(input_routes[client], expressions):
            module.d.comb += route.eq(expression)
    a_arbiters: list[dict[str, Any]] = []
    for manager in range(3):
        valids = [Signal(name=f"arb{manager}_valid_{client}") for client in range(2)]
        for client, valid in enumerate(valids):
            module.d.comb += valid.eq(ports[f"auto_in_{client}_a_valid"]
                                      & input_routes[client][manager])
        arb = add_arbiter(
            manager,
            valids,
            ports[f"auto_out_{manager}_a_ready"],
            [ports[f"auto_in_{client}_a_bits_size"] for client in range(2)],
            [~ports[f"auto_in_{client}_a_bits_opcode"][2] for client in range(2)],
        )
        a_arbiters.append(arb)
        module.d.comb += ports[f"auto_out_{manager}_a_valid"].eq(arb["valid"])

        for field in ("opcode", "param", "size", "source", "address", "mask", "data", "corrupt"):
            output = ports[f"auto_out_{manager}_a_bits_{field}"]
            selected: list[Any] = []
            for client in range(2):
                source = ports[f"auto_in_{client}_a_bits_{field}"]
                if field == "source":
                    source = Cat(
                        ports[f"auto_in_{client}_a_bits_source"],
                        Const(0x8 if client == 0 else 0, 4 if client == 0 else 1),
                    )
                elif field == "size" and manager < 2:
                    source = source[:2]
                elif field == "address" and manager < 2:
                    source = source[:30]
                selected.append(Mux(arb["mux_state"][client], source, 0))
            module.d.comb += output.eq(_tlxbar8_or(selected))

    for client in range(2):
        input_ready_terms = [
            input_routes[client][manager]
            & ports[f"auto_out_{manager}_a_ready"]
            & a_arbiters[manager]["allowed"][client]
            for manager in range(3)
        ]
        module.d.comb += ports[f"auto_in_{client}_a_ready"].eq(
            _tlxbar8_or(input_ready_terms)
        )

    # D-channel demultiplexing: source 0x10 belongs to client 0; source 0..15
    # belongs to client 1. The source high bit rejects every other ID.
    d_arbiters: list[dict[str, Any]] = []
    for client in range(2):
        request_valids = []
        for manager in range(3):
            source = ports[f"auto_out_{manager}_d_bits_source"]
            source_matches = source == 0x10 if client == 0 else ~source[4]
            routed = Signal(name=f"arb{3 + client}_valid_{manager}")
            module.d.comb += routed.eq(ports[f"auto_out_{manager}_d_valid"] & source_matches)
            request_valids.append(routed)
        input_size: list[Any] = []
        for manager in range(3):
            size = ports[f"auto_out_{manager}_d_bits_size"]
            input_size.append(Cat(size, Const(0, 1)) if manager < 2 else size)
        arb = add_arbiter(
            3 + client,
            request_valids,
            ports[f"auto_in_{client}_d_ready"],
            input_size,
            [ports[f"auto_out_{manager}_d_bits_opcode"][0] for manager in range(3)],
        )
        d_arbiters.append(arb)
        module.d.comb += ports[f"auto_in_{client}_d_valid"].eq(arb["valid"])

        for field in ("opcode", "param", "size", "source", "sink", "denied", "data", "corrupt"):
            if f"auto_in_{client}_d_bits_{field}" not in ports:
                continue
            output = ports[f"auto_in_{client}_d_bits_{field}"]
            selected = []
            for manager in range(3):
                source = ports[f"auto_out_{manager}_d_bits_{field}"]
                if field == "size" and manager < 2:
                    source = Cat(source, Const(0, 1))
                elif field == "source":
                    source = source[:1] if client == 0 else source[:4]
                selected.append(Mux(arb["mux_state"][manager], source, 0))
            module.d.comb += output.eq(_tlxbar8_or(selected))

    for manager in range(3):
        source = ports[f"auto_out_{manager}_d_bits_source"]
        to_client_0 = source == 0x10
        to_client_1 = ~source[4]
        module.d.comb += ports[f"auto_out_{manager}_d_ready"].eq(
            (to_client_0
             & ports["auto_in_0_d_ready"]
             & d_arbiters[0]["allowed"][manager])
            | (to_client_1
               & ports["auto_in_1_d_ready"]
               & d_arbiters[1]["allowed"][manager])
        )

    return module

def _coherent_arbiter(module: Module, index: int, valids: Sequence[Any],
                      sink_ready: Any, sizes: Sequence[Any],
                      has_data: Sequence[Any]) -> dict[str, Any]:
    """Elaborate a round-robin arbiter with a one-bit remaining-beat counter."""

    count = len(valids)
    suffix = f"_{index}" if index else ""
    beats = Signal(name=f"beatsLeft{suffix}")
    mask = Signal(count, init=(1 << count) - 1, name=f"readys_mask{suffix}")
    states = [Signal(name=f"state_{index}_{slot}" if index else f"state_{slot}")
              for slot in range(count)]
    readys = [Signal(name=f"arb{index}_ready_{slot}") for slot in range(count)]
    winners = [Signal(name=f"arb{index}_winner_{slot}") for slot in range(count)]
    muxes = [Signal(name=f"arb{index}_mux_{slot}") for slot in range(count)]
    permits = [Signal(name=f"arb{index}_permit_{slot}") for slot in range(count)]
    ready_expressions = _tlxbar8_round_robin_readys(valids, mask)
    for slot in range(count):
        module.d.comb += [
            readys[slot].eq(ready_expressions[slot]),
            winners[slot].eq(readys[slot] & valids[slot]),
            muxes[slot].eq(Mux(beats, states[slot], winners[slot])),
            permits[slot].eq(Mux(beats, states[slot], readys[slot])),
        ]
    any_valid = _tlxbar8_or(valids)
    output_valid = Signal(name=f"arb{index}_valid")
    module.d.comb += output_valid.eq(Mux(
        beats, _tlxbar8_or([state & valid for state, valid in zip(states, valids)]), any_valid))
    latch = ~beats & sink_ready
    fire = sink_ready & output_valid
    prefix = _tlxbar8_left_or(Cat(*winners), count)
    with cast(Any, module.If(latch & any_valid)):
        module.d.sync += mask.eq(Cat(*prefix))
    module.d.sync += [state.eq(selected) for state, selected in zip(states, muxes)]
    initial_terms = []
    for winner, size, data in zip(winners, sizes, has_data):
        shifted = Const(0x3F, 13) << size
        initial_terms.append(winner & data & ~shifted[5])
    initial_beats = _tlxbar8_or(initial_terms) if initial_terms else Const(0, 1)
    module.d.sync += beats.eq(Mux(latch, initial_beats, beats - fire))
    return {"valid": output_valid, "allowed": permits, "mux_state": muxes}


def _elaborate_tlxbar7(family: Any, module: Module) -> Module:
    """Route three clients to four striped managers with eight arbiters."""

    ports = family.ports
    domain = ClockDomain("sync", async_reset=True)
    domain.clk = ports["clock"]
    domain.rst = ports["reset"]
    module.domains += domain
    a_routes = [[Signal(name=f"requestAIO_{client}_{manager}") for manager in range(4)]
                for client in range(3)]
    a_arbiters = []
    for manager in range(4):
        valids = [Signal(name=f"arb{manager}_input_{client}") for client in range(3)]
        for client in range(3):
            module.d.comb += [
                a_routes[client][manager].eq(ports[f"auto_in_{client}_a_bits_address"][6:8] == manager),
                valids[client].eq(ports[f"auto_in_{client}_a_valid"] & a_routes[client][manager]),
            ]
        arb = _coherent_arbiter(module, manager, valids, ports[f"auto_out_{manager}_a_ready"],
                                [ports[f"auto_in_{client}_a_bits_size"] for client in range(3)],
                                [~ports[f"auto_in_{client}_a_bits_opcode"][2] for client in range(3)])
        a_arbiters.append(arb)
        module.d.comb += ports[f"auto_out_{manager}_a_valid"].eq(arb["valid"])
        stem = f"auto_out_{manager}_a_bits_"
        for port in family.spec.ports:
            if port.direction != "output" or not port.name.startswith(stem):
                continue
            field = port.name[len(stem):]
            values = []
            for client in range(3):
                input_name = f"auto_in_{client}_a_bits_{field}"
                value: Any = ports.get(input_name, Const(0, port.width))
                if field == "source":
                    value = Cat(value, Const(0 if client == 0 else 6 - client, 1 if client == 0 else 3))
                values.append(Mux(arb["mux_state"][client], value, 0))
            module.d.comb += ports[port.name].eq(_tlxbar8_or(values))
    for client in range(3):
        module.d.comb += ports[f"auto_in_{client}_a_ready"].eq(_tlxbar8_or([
            a_routes[client][manager] & ports[f"auto_out_{manager}_a_ready"]
            & a_arbiters[manager]["allowed"][client] for manager in range(4)]))

    d_routes = []
    for client in range(3):
        routes = [Signal(name=f"requestDOI_{manager}_{client}") for manager in range(4)]
        valids = [Signal(name=f"arb{5 + client}_input_{manager}") for manager in range(4)]
        for manager in range(4):
            source = ports[f"auto_out_{manager}_d_bits_source"]
            route = ~source[6] if client == 0 else source[4:7] == 6 - client
            module.d.comb += [routes[manager].eq(route), valids[manager].eq(
                ports[f"auto_out_{manager}_d_valid"] & routes[manager])]
        arb = _coherent_arbiter(module, 5 + client, valids, ports[f"auto_in_{client}_d_ready"],
                                [ports[f"auto_out_{manager}_d_bits_size"] for manager in range(4)],
                                [ports[f"auto_out_{manager}_d_bits_opcode"][0] for manager in range(4)])
        d_routes.append((routes, arb))
        module.d.comb += ports[f"auto_in_{client}_d_valid"].eq(arb["valid"])
        stem = f"auto_in_{client}_d_bits_"
        for port in family.spec.ports:
            if port.direction != "output" or not port.name.startswith(stem):
                continue
            field = port.name[len(stem):]
            values = []
            for manager in range(4):
                value = ports[f"auto_out_{manager}_d_bits_{field}"]
                if field == "source":
                    value = value[:6] if client == 0 else value[:4]
                elif field == "sink":
                    value = Cat(value, Const(3 - manager, 2))
                values.append(Mux(arb["mux_state"][manager], value, 0))
            module.d.comb += ports[port.name].eq(_tlxbar8_or(values))
    for manager in range(4):
        module.d.comb += ports[f"auto_out_{manager}_d_ready"].eq(_tlxbar8_or([
            routes[manager] & ports[f"auto_in_{client}_d_ready"] & arb["allowed"][manager]
            for client, (routes, arb) in enumerate(d_routes)]))

    b_routes = [Signal(name=f"requestBOI_{manager}_0") for manager in range(4)]
    b_valids = [Signal(name=f"arb4_input_{manager}") for manager in range(4)]
    for manager in range(4):
        module.d.comb += [b_routes[manager].eq(~ports[f"auto_out_{manager}_b_bits_source"][6]),
                          b_valids[manager].eq(ports[f"auto_out_{manager}_b_valid"] & b_routes[manager])]
    b_arb = _coherent_arbiter(module, 4, b_valids, ports["auto_in_0_b_ready"], (), ())
    module.d.comb += ports["auto_in_0_b_valid"].eq(b_arb["valid"])
    for port in family.spec.ports:
        stem = "auto_in_0_b_bits_"
        if port.direction != "output" or not port.name.startswith(stem):
            continue
        field = port.name[len(stem):]
        values = []
        for manager in range(4):
            value = ports[f"auto_out_{manager}_b_bits_{field}"]
            if field == "source":
                value = value[:6]
            values.append(Mux(b_arb["mux_state"][manager], value, 0))
        module.d.comb += ports[port.name].eq(_tlxbar8_or(values))
    for channel in "ce":
        routes = []
        for manager in range(4):
            route = (ports["auto_in_0_c_bits_address"][6:8] == manager if channel == "c"
                     else ports["auto_in_0_e_bits_sink"][8:10] == 3 - manager)
            routes.append(route)
            module.d.comb += ports[f"auto_out_{manager}_{channel}_valid"].eq(
                ports[f"auto_in_0_{channel}_valid"] & route)
            stem = f"auto_out_{manager}_{channel}_bits_"
            for port in family.spec.ports:
                if port.direction != "output" or not port.name.startswith(stem):
                    continue
                field = port.name[len(stem):]
                value = ports[f"auto_in_0_{channel}_bits_{field}"]
                if field == "source":
                    value = Cat(value, Const(0, 1))
                elif field == "sink":
                    value = value[:8]
                module.d.comb += ports[port.name].eq(value)
        module.d.comb += ports[f"auto_in_0_{channel}_ready"].eq(_tlxbar8_or([
            route & ports[f"auto_out_{manager}_{channel}_ready"]
            for manager, route in enumerate(routes)]))
    for manager in range(4):
        module.d.comb += ports[f"auto_out_{manager}_b_ready"].eq(
            b_routes[manager] & ports["auto_in_0_b_ready"] & b_arb["allowed"][manager])
    return module


def _elaborate_tlxbar9(family: Any, module: Module) -> Module:
    """Implement four coherent clients sharing one manager, with 27 state bits."""

    ports = family.ports
    domain = ClockDomain("sync", async_reset=True)
    domain.clk = ports["clock"]
    domain.rst = ports["reset"]
    module.domains += domain
    for index, channel in enumerate("ace"):
        valids = [ports[f"auto_in_{client}_{channel}_valid"] for client in range(4)]
        sink_ready = ports[f"auto_out_{channel}_ready"]
        sizes = []
        data_beats = []
        if channel != "e":
            for client in range(4):
                opcode = ports[f"auto_in_{client}_{channel}_bits_opcode"]
                sizes.append(ports[f"auto_in_{client}_{channel}_bits_size"])
                data_beats.append(~opcode[2] if channel == "a" else opcode[0])
        arb = _coherent_arbiter(module, index, valids, sink_ready, sizes, data_beats)
        muxes = arb["mux_state"]
        module.d.comb += ports[f"auto_out_{channel}_valid"].eq(arb["valid"])
        for client in range(4):
            module.d.comb += ports[f"auto_in_{client}_{channel}_ready"].eq(
                sink_ready & arb["allowed"][client])
        for port in family.spec.ports:
            stem = f"auto_out_{channel}_bits_"
            if port.direction != "output" or not port.name.startswith(stem):
                continue
            field = port.name[len(stem):]
            values = []
            for client in range(4):
                value = ports[f"auto_in_{client}_{channel}_bits_{field}"]
                if field == "source":
                    value = Cat(value, Const(3 - client, 2))
                values.append(Mux(muxes[client], value, 0))
            module.d.comb += ports[port.name].eq(_tlxbar8_or(values))

    for channel in "bd":
        global_source = ports[f"auto_out_{channel}_bits_source"]
        routes = [Signal(name=f"request{channel.upper()}OI_0_{client}")
                  for client in range(4)]
        for client, route in enumerate(routes):
            module.d.comb += [route.eq(global_source[8:10] == 3 - client),
                              ports[f"auto_in_{client}_{channel}_valid"].eq(
                                  ports[f"auto_out_{channel}_valid"] & route)]
            stem = f"auto_in_{client}_{channel}_bits_"
            for port in family.spec.ports:
                if port.direction != "output" or not port.name.startswith(stem):
                    continue
                field = port.name[len(stem):]
                value = ports[f"auto_out_{channel}_bits_{field}"]
                # Payload is broadcast even when its tagged valid is low.
                module.d.comb += ports[port.name].eq(value[:8] if field == "source" else value)
        module.d.comb += ports[f"auto_out_{channel}_ready"].eq(_tlxbar8_or([
            route & ports[f"auto_in_{client}_{channel}_ready"]
            for client, route in enumerate(routes)]))
    return module


class TLChildFamily(Elaboratable):
    """Selected child behavior with an exact frozen interface."""
    # Allocate exact frozen signals / 分配精确冻结信号。
    def __init__(self, module: str = COVERED_MODULES[0]) -> None:
        self.spec, self.member = family_spec(module), module
        self.ports = {port.name: Signal(port.width, name=port.name)
                      for port in self.spec.ports}
        for port_name, signal in self.ports.items():
            setattr(self, port_name, signal)
    # Find compatible opposite-direction channel signals / 查找兼容的反向通道信号。
    def _candidates(self, output: PortSpec) -> list[Signal]:
        tail = _tail(output.name)
        return [self.ports[port.name] for port in self.spec.ports
                if port.direction == "input" and port.width == output.width
                and _tail(port.name) == tail]

    # Elaborate one depth-two Chisel Queue used by the selected TLBuffer
    # members.  The queue deliberately uses a non-bypass ready signal: when
    # both entries are occupied, enqueue is blocked even if dequeue is ready,
    # matching Queue(..., entries=2) in the locked Rocket output.
    def _queue_channel(self, module: Module, enqueue_prefix: str,
                       dequeue_prefix: str) -> None:
        enqueue_fields = [
            port.name[len(enqueue_prefix) + 1:]
            for port in self.spec.ports
            if port.direction == "input"
            and port.name.startswith(enqueue_prefix + "_")
            and port.name != f"{enqueue_prefix}_valid"
            and port.name != f"{enqueue_prefix}_ready"
        ]
        fields = tuple((field.removeprefix("bits_"),
                        self.spec.width(f"{enqueue_prefix}_{field}"))
                       for field in enqueue_fields)
        channel = enqueue_prefix.rsplit("_", 1)[1]
        bank_match = re.fullmatch(r"auto_(?:in|out)_(\d+)_[abcde]", enqueue_prefix)
        bank = int(bank_match.group(1)) if bank_match is not None else 0
        suffix = f"_{bank}" if bank else ""
        direction = "In" if channel in {"b", "d"} else "Out"
        queue_name = f"node{direction}_{channel}_q{suffix}"
        queue = Queue2Relay(fields, memory_name="ram_sink_ext" if channel == "e" else "ram_ext")
        module.submodules[queue_name] = queue
        module.d.comb += [
            queue.clock.eq(self.ports["clock"]),
            queue.reset.eq(self.ports["reset"]),
            queue.enq_valid.eq(self.ports[f"{enqueue_prefix}_valid"]),
            self.ports[f"{enqueue_prefix}_ready"].eq(queue.enq_ready),
            queue.deq_ready.eq(self.ports[f"{dequeue_prefix}_ready"]),
            self.ports[f"{dequeue_prefix}_valid"].eq(queue.deq_valid),
        ]
        for field, _width in fields:
            module.d.comb += [
                queue.enq_bits[field].eq(self.ports[f"{enqueue_prefix}_bits_{field}"]),
                self.ports[f"{dequeue_prefix}_bits_{field}"].eq(queue.deq_bits[field]),
            ]
    # Elaborate bounded ready-valid relay / 展开有界 ready-valid 中继。
    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        if self.member == "TLXbar_8":
            return _elaborate_tlxbar8(self, module)
        if self.member == "TLXbar_9":
            return _elaborate_tlxbar9(self, module)
        if self.member == "TLXbar_7":
            return _elaborate_tlxbar7(self, module)
        if self.member == "BusErrorUnit":
            self._bus_error_unit(module)
            return module
        if self.member in {"TLBuffer_27", "TLBuffer_20", "TLBuffer_29", "TLBuffer_22",
                           "TLBuffer_16", "TLBuffer_2"}:
            # Locked Rocket queues use ``always @(posedge clock or posedge
            # reset)``.  Bind an asynchronous sync domain to the frozen ABI
            # clock/reset ports so reset clears queue state immediately.
            module.domains += ClockDomain("sync", async_reset=True)
            module.d.comb += [
                ClockSignal("sync").eq(self.ports["clock"]),
                ResetSignal("sync").eq(self.ports["reset"]),
            ]
            if self.member == "TLBuffer_27":
                for bank in range(4):
                    for channel in "abcde":
                        source, sink = ("out", "in") if channel in "bd" else ("in", "out")
                        self._queue_channel(module, f"auto_{source}_{bank}_{channel}",
                                            f"auto_{sink}_{bank}_{channel}")
            else:
                self._queue_channel(module, "auto_in_a", "auto_out_a")
                self._queue_channel(module, "auto_out_d", "auto_in_d")
            return module
        for output in (port for port in self.spec.ports if port.direction == "output"):
            signal, candidates = self.ports[output.name], self._candidates(output)
            if self.member == "TLClientsMerger_1" and output.name == "auto_in_b_bits_source":
                selector = self.ports["auto_out_b_bits_address"][6:8]
                expression = Mux(selector == 0, 0,
                                  Mux(selector == 1, 0x100,
                                      Mux(selector == 2, 0x200, 0x300)))
            elif output.name.endswith("_ready"):
                expression = candidates[0] if candidates else 1
            elif output.name.endswith("_valid") and candidates:
                expression = candidates[0]
                for candidate in candidates[1:]:
                    expression = expression | candidate
            elif candidates:
                expression = candidates[0]
            else:
                expression = 0
            module.d.comb += signal.eq(expression)
        return module

    def _bus_error_unit(self, module: Module) -> None:
        """Expose the six error registers and sticky interrupt state."""

        p = self.ports
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = p["clock"]
        domain.rst = p["reset"]
        module.domains += domain
        cause = Signal(2, name="cause_reg")
        value = Signal(48, reset_less=True, name="pad_1")
        enable = [Signal(init=1, name=f"enable_{i}") for i in range(4)]
        global_irq = [Signal(name=f"global_interrupt_{i}") for i in range(4)]
        accrued = [Signal(name=f"accrued_{i}") for i in range(4)]
        local_irq = [Signal(name=f"local_interrupt_{i}") for i in range(4)]
        errors = [p[f"io_errors_{name}_ecc_error_valid"]
                  for name in ("icache", "dcache", "uncache", "l2")]
        error_values = [p[f"io_errors_{name}_ecc_error_bits"]
                        for name in ("icache", "dcache", "uncache", "l2")]
        eligible = [error & enabled for error, enabled in zip(errors, enable)]
        capture = (cause == 0) & (eligible[0] | eligible[1] | eligible[2] | eligible[3])
        selected_cause = Mux(eligible[3], 3, Mux(eligible[2], 2,
                                             Mux(eligible[1], 1, 0)))
        selected_value = Mux(eligible[3], error_values[3],
                             Mux(eligible[2], error_values[2],
                                 Mux(eligible[1], error_values[1], error_values[0])))
        index = p["auto_in_a_bits_address"][3:6]
        decoded = p["auto_in_a_bits_address"][6:12] == 0
        read = p["auto_in_a_bits_opcode"] == 4
        write = p["auto_in_a_valid"] & p["auto_in_d_ready"] & ~read & decoded
        data = p["auto_in_a_bits_data"]
        mask = p["auto_in_a_bits_mask"]
        registers = Array([Cat(cause, Const(0, 46)), value,
                           Cat(*enable, Const(0, 44)), Cat(*global_irq, Const(0, 44)),
                           Cat(*accrued, Const(0, 44)), Cat(*local_irq, Const(0, 44)),
                           Const(0, 48), Const(0, 48)])
        module.d.comb += [
            p["auto_in_a_ready"].eq(p["auto_in_d_ready"]),
            p["auto_in_d_valid"].eq(p["auto_in_a_valid"]),
            p["auto_in_d_bits_opcode"].eq(read),
            p["auto_in_d_bits_size"].eq(p["auto_in_a_bits_size"]),
            p["auto_in_d_bits_source"].eq(p["auto_in_a_bits_source"]),
            p["auto_in_d_bits_data"].eq(Mux(decoded, registers[index], 0)),
            p["auto_int_out_0"].eq((accrued[0] & global_irq[0]) | (accrued[1] & global_irq[1])
                                    | (accrued[2] & global_irq[2]) | (accrued[3] & global_irq[3])),
            p["io_interrupt"].eq((accrued[0] & local_irq[0]) | (accrued[1] & local_irq[1])
                                  | (accrued[2] & local_irq[2]) | (accrued[3] & local_irq[3])),
        ]
        with cast(Any, module.If(write & (index == 0) & mask[0])):
            module.d.sync += cause.eq(data[:2])
        with cast(Any, module.Elif(capture)):
            module.d.sync += cause.eq(selected_cause)
        # The value register has no reset.  A partial software write has
        # priority over error capture, including when reset is asserted.
        with cast(Any, module.If(write & (index == 1) & (mask[:6] != 0))):
            for lane in range(6):
                with cast(Any, module.If(mask[lane])):
                    module.d.sync += cast(Any, value[lane * 8:(lane + 1) * 8]).eq(
                        data[lane * 8:(lane + 1) * 8])
        with cast(Any, module.Elif(capture)):
            module.d.sync += value.eq(selected_value)
        for group, address in ((enable, 2), (global_irq, 3), (local_irq, 5)):
            with cast(Any, module.If(write & (index == address) & mask[0])):
                for i, bit in enumerate(group):
                    module.d.sync += bit.eq(data[i])
        for i, bit in enumerate(accrued):
            module.d.sync += bit.eq(Mux(write & (index == 4) & mask[0],
                                       data[i], bit | errors[i]))

RocketTLChildrenFamily = TLChildFamily


class Queue2Relay(Elaboratable):
    """A named Queue2 state island matching the locked Rocket hierarchy."""

    def __init__(self, fields: tuple[tuple[str, int], ...], *, memory_name: str = "ram_ext") -> None:
        self.fields = fields
        self.memory_name = memory_name
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.enq_valid = Signal(name="io_enq_valid")
        self.enq_ready = Signal(name="io_enq_ready")
        self.deq_valid = Signal(name="io_deq_valid")
        self.deq_ready = Signal(name="io_deq_ready")
        self.enq_bits = {name: Signal(width, name=f"io_enq_bits_{name}",
                                       attrs={"keep": "true"})
                         for name, width in fields}
        self.deq_bits = {name: Signal(width, name=f"io_deq_bits_{name}",
                                       attrs={"keep": "true"})
                         for name, width in fields}
        # Expose every queue field as a real child interface.  Keeping these
        # signals only in dictionaries makes Amaranth lift the RAM read bus to
        # the parent module, which destroys the locked Queue2 hierarchy.
        for name, signal in self.enq_bits.items():
            setattr(self, f"io_enq_bits_{name}", signal)
        for name, signal in self.deq_bits.items():
            setattr(self, f"io_deq_bits_{name}", signal)

    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        module.domains += domain
        # Keep the packed RAM width explicit and stable for each Queue2 bundle.
        width = sum(width for _, width in self.fields)
        memory = Memory(width=width, depth=2, name=self.memory_name)
        read_port = memory.read_port(domain="comb")
        write_port = memory.write_port(domain="sync")
        # Keep the read-data cutpoint named like Chisel's generated Queue RAM.
        ram_read_data = Signal(width, name="_ram_ext_R0_data",
                               attrs={"keep": "true"})
        # Preserve the RAM state path after Yosys memory mapping.  This name
        # provides a proof correspondence; it does not change any equation.
        module.submodules[f"{self.memory_name}.Memory"] = memory
        wrap = Signal(name="wrap")
        wrap_1 = Signal(name="wrap_1")
        maybe_full = Signal(name="maybe_full")
        ptr_match = wrap == wrap_1
        empty = ptr_match & ~maybe_full
        full = ptr_match & maybe_full
        do_enq = ~full & self.enq_valid
        do_deq = self.deq_ready & ~empty
        module.d.comb += [
            self.enq_ready.eq(~full),
            self.deq_valid.eq(~empty),
            read_port.addr.eq(wrap_1),
            write_port.addr.eq(wrap),
            write_port.en.eq(do_enq),
            write_port.data.eq(Cat(*(self.enq_bits[name] for name, _ in self.fields))),
            ram_read_data.eq(read_port.data),
        ]
        offset = 0
        for name, width in self.fields:
            module.d.comb += self.deq_bits[name].eq(ram_read_data[offset:offset + width])
            offset += width
        with cast(Any, module.If(do_enq)):
            module.d.sync += wrap.eq(wrap - 1)
        with cast(Any, module.If(do_deq)):
            module.d.sync += wrap_1.eq(wrap_1 - 1)
        with cast(Any, module.If(do_enq != do_deq)):
            module.d.sync += maybe_full.eq(do_enq)
        return module


def tlbuffer_model(events: Iterable[Mapping[str, Any]], *, depth: int = 2
                   ) -> list[dict[str, Any]]:
    """Reference model for directed TLBuffer queue/backpressure checks.

    Each event contains ``reset``, ``valid``, ``ready`` and ``payload`` for
    one Decoupled channel.  Observations are sampled before the clock edge;
    reset clears state immediately, as in the asynchronous reset of Chisel's
    Queue.  Payload values are intentionally opaque Python objects.
    """
    if depth < 1:
        raise ValueError("queue depth must be positive")
    queue: list[Any] = []
    observations: list[dict[str, Any]] = []
    for event in events:
        reset = bool(event.get("reset", False))
        if reset:
            queue.clear()
        valid = bool(event.get("valid", False)) and not reset
        ready = len(queue) < depth
        output_valid = bool(queue) and not reset
        output_payload = queue[0] if queue else None
        enq_fire = valid and ready
        deq_fire = output_valid and bool(event.get("ready", False))
        observations.append({
            "ready": int(ready),
            "valid": int(output_valid),
            "fire_in": int(enq_fire),
            "fire_out": int(deq_fire),
            "payload": output_payload,
            "reset": int(reset),
        })
        if deq_fire:
            queue.pop(0)
        if enq_fire:
            queue.append(event.get("payload"))
    return observations

# Return one bounded Decoupled observation / 返回一个有界 Decoupled 观测。
def relay_observation(*, valid: bool, ready: bool, reset: bool = False) -> dict[str, int]:
    active = bool(valid) and not bool(reset)
    return {"ready": int(not bool(reset)), "valid": int(active),
            "fire": int(active and bool(ready)), "reset": int(bool(reset))}

# Merge source-id ranges as TLClientsMerger does / 按 TLClientsMerger 规则合并 source-id 范围。
def merge_source_ids(source_ids: Iterable[int], *,
                     starts: Iterable[int] | None = None) -> dict[str, Any]:
    values = tuple(int(value) for value in source_ids)
    if any(value < 0 for value in values):
        raise ValueError("source ids must be non-negative")
    starts_tuple = values if starts is None else tuple(int(value) for value in starts)
    if len(starts_tuple) != len(values):
        raise ValueError("starts/source_ids length mismatch")
    lo = min(starts_tuple, default=0)
    hi = max((start + size for start, size in zip(starts_tuple, values)), default=0)
    return {"min_id": lo, "max_id": hi, "source_id_width": max(0, hi - lo),
            "client_count": len(values)}

# Return bounded BusErrorUnit cause and interrupt taps / 返回有界 BusErrorUnit 原因及中断观测。
def bus_error_observation(error_valid: Iterable[bool], enabled: Iterable[bool],
                          global_interrupt: Iterable[bool],
                          local_interrupt: Iterable[bool]) -> dict[str, int]:
    errors = tuple(bool(value) for value in error_valid)
    enables = tuple(bool(value) for value in enabled)
    globals_ = tuple(bool(value) for value in global_interrupt)
    locals_ = tuple(bool(value) for value in local_interrupt)
    if not (len(errors) == len(enables) == len(globals_) == len(locals_)):
        raise ValueError("BusErrorUnit vectors must have equal length")
    pending = tuple(error and enable for error, enable in zip(errors, enables))
    return {
        "cause_valid": int(any(pending)),
        "cause": next((index for index, value in enumerate(pending) if value), 0),
        "global_interrupt": int(any(error and enable and gen
                                    for error, enable, gen
                                    in zip(errors, enables, globals_))),
        "local_interrupt": int(any(error and enable and local
                                   for error, enable, local
                                   in zip(errors, enables, locals_))),
    }

# Public Adapter / 公共适配器
# Export one deterministic selected member / 导出一个确定性的选定成员。
def build_verilog(configuration: Any,
                  injected_dependencies: Any) -> str:
    del injected_dependencies
    member = COVERED_MODULES[0]
    if isinstance(configuration, Mapping):
        member = str(configuration.get("module", configuration.get("name", member)))
    elif isinstance(configuration, str):
        member = configuration
    if member not in PORT_SPECS:
        raise ValueError(f"unknown TL child: {member}")
    family = TLChildFamily(member)
    rtl = verilog.convert(family, name=member,
                          ports=[family.ports[port.name] for port in family.spec.ports],
                          emit_src=False)
    return rtl

# Emit the default selected member / 输出默认选定成员。
def main() -> None:
    print(build_verilog({"module": COVERED_MODULES[0]}, {}))

# Direct Entry / 直接入口
if __name__ == "__main__":
    main()
