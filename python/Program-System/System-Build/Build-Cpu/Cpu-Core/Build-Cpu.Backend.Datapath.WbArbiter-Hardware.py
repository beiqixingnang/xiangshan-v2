"""V2 write-back dispatch, collision arbitration, and data-path closure.
V2 写回分发、冲突仲裁及数据通路闭包。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from amaranth import Const, Elaboratable, Module, Mux, Signal


# =============================================================================
# Module Contract
# =============================================================================
# WbArbiter.scala contains three connected surfaces.  The dispatcher fans one
# ExuOutput to accepted destinations; RealWBCollideChecker groups write-back
# inputs by physical-register port and applies RealWBArbiter priority; and
# WbDataPath combines integer, floating, vector, v0, vl, and memory EXUs.
# WbArbiter.scala 包含三个相连表面：分发器按接受条件扇出 ExuOutput；
# RealWBCollideChecker 按物理寄存器写口分组并应用 RealWBArbiter 优先级；
# WbDataPath 合并整数、浮点、向量、v0、vl 及内存 EXU。
__all__ = [
    "WbExuAttr",
    "WbDataPathConfig",
    "arbiterCtrl",
    "writeback_observation",
    "RealWBArbiter",
    "WbArbiterDispatcher",
    "RealWBCollideChecker",
    "WbDataPath",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class WbExuAttr:
    """Serializable EXU write-back attributes. / 可序列化的 EXU 写回属性。"""

    name: str = "exu"
    writeIntRf: bool = False
    writeFpRf: bool = False
    writeVfRf: bool = False
    writeV0Rf: bool = False
    writeVlRf: bool = False
    hasUncertainLatency: bool = False
    hasNoDataWB: bool = False
    isHighestWBPriority: bool = False
    isVfExeUnit: bool = False
    isFpExeUnit: bool = False
    hasVLoadFu: bool = False
    isMemExeUnit: bool = False

    # Construct attributes from a serializable mapping or existing record.
    # 从可序列化映射或现有记录构造属性。
    @classmethod
    # Construct an attribute record from a mapping. / 从映射构造属性记录。
    def from_value(cls, value: Any) -> "WbExuAttr":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            names = {field for field in cls.__dataclass_fields__}
            return cls(**{key: item for key, item in value.items() if key in names})
        raise TypeError("EXU attributes must be WbExuAttr or dict")


@dataclass(frozen=True)
class WbDataPathConfig:
    """Explicit V2 write-back geometry and EXU closure.
    显式的 V2 写回几何与 EXU 闭包。
    """

    intExus: tuple = ()
    fpExus: tuple = ()
    vfExus: tuple = ()
    intWbPorts: tuple = ()
    fpWbPorts: tuple = ()
    vfWbPorts: tuple = ()
    v0WbPorts: tuple = ()
    vlWbPorts: tuple = ()
    intPortMax: int = 0
    fpPortMax: int = 0
    vfPortMax: int = 0
    v0PortMax: int = 0
    vlPortMax: int = 0
    isVecSchd: bool = False
    dataWidth: int = 64
    addrWidth: int = 8
    RobPtrWidth: int = 10
    memExus: tuple = ()
    memWbPorts: tuple = ()

    # Validate widths and normalize the explicit closure boundary. / 校验位宽并规范化显式闭包边界。
    def __post_init__(self) -> None:
        if self.dataWidth < 1 or self.addrWidth < 1 or self.RobPtrWidth < 1:
            raise ValueError("all write-back widths must be positive")
        if min(self.intPortMax, self.fpPortMax, self.vfPortMax,
               self.v0PortMax, self.vlPortMax) < 0:
            raise ValueError("write-back port maxima cannot be negative")

    # Return all EXUs in V2 WbDataPath flattening order. / 返回 V2 WbDataPath 展平顺序的全部 EXU。
    @property
    # Return all EXUs in V2 WbDataPath flattening order. / 返回 V2 WbDataPath 展平顺序的全部 EXU。
    def allExus(self) -> tuple[WbExuAttr, ...]:
        values: list[WbExuAttr] = []
        for group in (self.intExus, self.fpExus, self.vfExus, self.memExus):
            values.extend(WbExuAttr.from_value(item) for item in group)
        return tuple(values)


# =============================================================================
# Implementation
# =============================================================================
# Compute V2's first-valid one-hot grant sequence. / 计算 V2 首个有效的一热授权序列。
def arbiterCtrl(request: Iterable[Any]) -> list[Any]:
    values = list(request)
    if not values:
        return []
    # Rocket's WBArbiter grants the first slot unconditionally and each later
    # slot only when every earlier slot is invalid.  The old mirror omitted the
    # final grant for n>2 and incorrectly gated slot zero by its request.
    # Rocket WBArbiter 的写回仲裁将首槽无条件置为 ready，后续槽仅在所有
    # 更高优先级槽无效时 ready；旧镜像在 n>2 时漏掉末槽且错误门控首槽。
    grants: list[Any] = [Const(1, 1)]
    prefix = values[0]
    for item in values[1:]:
        grants.append(~prefix)
        prefix = prefix | item
    return grants


def writeback_observation(valid: list[bool], ready: bool = True) -> dict[str, object]:
    """Return first-valid writeback grant and selected index. / 返回首个有效写回授权与索引。"""

    if not valid:
        return {"grants": [], "selected": -1, "fire": 0}
    selected = next((index for index, item in enumerate(valid) if item), -1)
    grants = [int(item and index == selected) for index, item in enumerate(valid)]
    return {"grants": grants, "selected": selected,
            "fire": int(selected >= 0 and bool(ready))}


class RealWBArbiter(Elaboratable):
    """Priority arbiter used by V2 write-back ports.
    V2 写回端口使用的优先级仲裁器。
    """

    # Construct decoupled input and valid output fields. / 构造解耦输入及有效输出字段。
    def __init__(self, dataWidth: int = 64, n: int = 2, addrWidth: int = 8) -> None:
        if int(dataWidth) < 1 or int(addrWidth) < 1 or int(n) < 1:
            raise ValueError("dataWidth, addrWidth, and n must be positive")
        self.dataWidth = int(dataWidth)
        self.addrWidth = int(addrWidth)
        self.n = int(n)
        self.in_valid = [Signal(name=f"io_in_{index}_valid") for index in range(self.n)]
        self.in_ready = [Signal(name=f"io_in_{index}_ready") for index in range(self.n)]
        self.in_bits = [Signal(self.dataWidth, name=f"io_in_{index}_bits_data") for index in range(self.n)]
        self.in_pdest = [Signal(self.addrWidth, name=f"io_in_{index}_bits_pdest") for index in range(self.n)]
        self.in_rfWen = [Signal(name=f"io_in_{index}_bits_rfWen") for index in range(self.n)]
        self.in_fpWen = [Signal(name=f"io_in_{index}_bits_fpWen") for index in range(self.n)]
        self.in_vecWen = [Signal(name=f"io_in_{index}_bits_vecWen") for index in range(self.n)]
        self.in_v0Wen = [Signal(name=f"io_in_{index}_bits_v0Wen") for index in range(self.n)]
        self.in_vlWen = [Signal(name=f"io_in_{index}_bits_vlWen") for index in range(self.n)]
        self.out_valid = Signal(name="io_out_valid")
        self.out_ready = Signal(name="io_out_ready", reset=1)
        self.out_bits = Signal(self.dataWidth, name="io_out_bits_data")
        self.out_pdest = Signal(self.addrWidth, name="io_out_bits_pdest")
        self.out_rfWen = Signal(name="io_out_bits_rfWen")
        self.out_fpWen = Signal(name="io_out_bits_fpWen")
        self.out_vecWen = Signal(name="io_out_bits_vecWen")
        self.out_v0Wen = Signal(name="io_out_bits_v0Wen")
        self.out_vlWen = Signal(name="io_out_bits_vlWen")
        self.out_fire = Signal(name="io_out_fire")
        self.chosen = Signal(max(1, (self.n - 1).bit_length()), name="io_chosen")

    # Elaborate lowest-index priority and ready propagation. / 展开低索引优先级与就绪传播。
    def elaborate(self, platform) -> Module:
        del platform
        module = Module()
        grants = arbiterCtrl(self.in_valid)
        selected_bits: Any = self.in_bits[-1]
        selected_pdest: Any = self.in_pdest[-1]
        selected_rf: Any = self.in_rfWen[-1]
        selected_fp: Any = self.in_fpWen[-1]
        selected_vec: Any = self.in_vecWen[-1]
        selected_v0: Any = self.in_v0Wen[-1]
        selected_vl: Any = self.in_vlWen[-1]
        for index in range(self.n - 2, -1, -1):
            selected_bits = Mux(self.in_valid[index], self.in_bits[index], selected_bits)
            selected_pdest = Mux(self.in_valid[index], self.in_pdest[index], selected_pdest)
            selected_rf = Mux(self.in_valid[index], self.in_rfWen[index], selected_rf)
            selected_fp = Mux(self.in_valid[index], self.in_fpWen[index], selected_fp)
            selected_vec = Mux(self.in_valid[index], self.in_vecWen[index], selected_vec)
            selected_v0 = Mux(self.in_valid[index], self.in_v0Wen[index], selected_v0)
            selected_vl = Mux(self.in_valid[index], self.in_vlWen[index], selected_vl)
        module.d.comb += [
            self.out_valid.eq(~grants[-1] | self.in_valid[-1]),
            self.out_bits.eq(selected_bits),
            self.out_pdest.eq(selected_pdest),
            self.out_rfWen.eq(selected_rf),
            self.out_fpWen.eq(selected_fp),
            self.out_vecWen.eq(selected_vec),
            self.out_v0Wen.eq(selected_v0),
            self.out_vlWen.eq(selected_vl),
            self.out_fire.eq(self.out_valid & self.out_ready),
        ]
        # Chisel's chosen field defaults to n-1 and is overwritten by each
        # valid input in descending order, yielding the lowest valid index.
        chosen = self.n - 1
        for index in range(self.n - 1, -1, -1):
            chosen = Mux(self.in_valid[index], index, chosen)
        module.d.comb += self.chosen.eq(chosen)
        for index, grant in enumerate(grants):
            module.d.comb += self.in_ready[index].eq((grant | ~self.in_valid[index]) & self.out_ready)
        return module


class WbArbiterDispatcher(Elaboratable):
    """Fan one write-back payload to accepted destinations.
    将一个写回载荷扇出到接受目的端。
    """

    # Construct dispatcher channels and optional acceptance callback. / 构造分发器通道及可选接受回调。
    def __init__(self, dataWidth: int = 64, n: int = 5, acceptCond: Any = None) -> None:
        if int(dataWidth) < 1 or int(n) < 1:
            raise ValueError("dataWidth and n must be positive")
        self.dataWidth = int(dataWidth)
        self.n = int(n)
        self.acceptCond = acceptCond
        self.in_valid = Signal(name="io_in_valid")
        self.in_ready = Signal(name="io_in_ready")
        self.in_bits = Signal(self.dataWidth, name="io_in_bits_data")
        self.acceptVec = [Signal(name=f"io_accept_{index}") for index in range(self.n)]
        self.notWrite = Signal(name="io_notWrite")
        self.out_valid = [Signal(name=f"io_out_{index}_valid") for index in range(self.n)]
        self.out_ready = [Signal(name=f"io_out_{index}_ready") for index in range(self.n)]
        self.out_bits = [Signal(self.dataWidth, name=f"io_out_{index}_bits_data") for index in range(self.n)]

    # Elaborate acceptance fanout and ready OR reduction. / 展开接受扇出与 ready 或归约。
    def elaborate(self, platform) -> Module:
        del platform
        module = Module()
        accepts = list(self.acceptVec)
        no_write: Any = self.notWrite
        if self.acceptCond is not None:
            result = self.acceptCond(self.in_bits)
            accepts = list(result[0])
            no_write = result[1]
            for index, expression in enumerate(accepts):
                module.d.comb += self.acceptVec[index].eq(expression)
            module.d.comb += self.notWrite.eq(no_write)
        ready_or: Any = Const(0, 1)
        for index in range(self.n):
            module.d.comb += [
                self.out_valid[index].eq(self.in_valid & accepts[index]),
                self.out_bits[index].eq(self.in_bits),
            ]
            ready_or = ready_or | (self.out_ready[index] & accepts[index])
        module.d.comb += self.in_ready.eq(ready_or | no_write)
        return module


class RealWBCollideChecker(Elaboratable):
    """Group write-back inputs by port and resolve collisions.
    按写口分组写回输入并解决冲突。
    """

    # Construct grouped inputs, outputs, and priority metadata. / 构造分组输入、输出及优先级元数据。
    def __init__(
        self,
        dataWidth: int = 64,
        inPorts: Iterable[int] = (),
        portRange: Iterable[int] = (),
        portMax: int | None = None,
        addrWidth: int = 8,
        priorities: Iterable[int] | None = None,
    ) -> None:
        if int(dataWidth) < 1 or int(addrWidth) < 1:
            raise ValueError("dataWidth and addrWidth must be positive")
        self.dataWidth = int(dataWidth)
        self.addrWidth = int(addrWidth)
        self.inPorts = tuple(int(item) for item in inPorts)
        self.portRange = tuple(int(item) for item in portRange)
        inferred = max(self.portRange + tuple(item for item in self.inPorts if item >= 0), default=0)
        self.portMax = inferred if portMax is None else max(0, int(portMax))
        priority_values = tuple(int(item) for item in priorities) if priorities is not None else tuple(range(len(self.inPorts)))
        if len(priority_values) < len(self.inPorts):
            priority_values += tuple(range(len(priority_values), len(self.inPorts)))
        self.priorities = priority_values
        groups: dict[int, list[int]] = {}
        for index, port in enumerate(self.inPorts):
            if port >= 0:
                groups.setdefault(port, []).append(index)
        self.inGroup = {
            port: tuple(sorted(indices, key=lambda item: (self.priorities[item], item)))
            for port, indices in groups.items()
            if port in self.portRange or not self.portRange
        }
        self.arbiters = {
            port: RealWBArbiter(self.dataWidth, len(indices), self.addrWidth)
            for port, indices in self.inGroup.items()
        }
        count = len(self.inPorts)
        self.in_valid = [Signal(name=f"io_in_{index}_valid") for index in range(count)]
        self.in_ready = [Signal(name=f"io_in_{index}_ready") for index in range(count)]
        self.in_bits = [Signal(self.dataWidth, name=f"io_in_{index}_bits_data") for index in range(count)]
        self.in_pdest = [Signal(self.addrWidth, name=f"io_in_{index}_bits_pdest") for index in range(count)]
        self.in_rfWen = [Signal(name=f"io_in_{index}_bits_rfWen") for index in range(count)]
        self.in_fpWen = [Signal(name=f"io_in_{index}_bits_fpWen") for index in range(count)]
        self.in_vecWen = [Signal(name=f"io_in_{index}_bits_vecWen") for index in range(count)]
        self.in_v0Wen = [Signal(name=f"io_in_{index}_bits_v0Wen") for index in range(count)]
        self.in_vlWen = [Signal(name=f"io_in_{index}_bits_vlWen") for index in range(count)]
        self.out_valid = [Signal(name=f"io_out_{port}_valid") for port in range(self.portMax + 1)]
        self.out_bits = [Signal(self.dataWidth, name=f"io_out_{port}_bits_data") for port in range(self.portMax + 1)]
        self.out_pdest = [Signal(self.addrWidth, name=f"io_out_{port}_bits_pdest") for port in range(self.portMax + 1)]
        self.out_rfWen = [Signal(name=f"io_out_{port}_bits_rfWen") for port in range(self.portMax + 1)]
        self.out_fpWen = [Signal(name=f"io_out_{port}_bits_fpWen") for port in range(self.portMax + 1)]
        self.out_vecWen = [Signal(name=f"io_out_{port}_bits_vecWen") for port in range(self.portMax + 1)]
        self.out_v0Wen = [Signal(name=f"io_out_{port}_bits_v0Wen") for port in range(self.portMax + 1)]
        self.out_vlWen = [Signal(name=f"io_out_{port}_bits_vlWen") for port in range(self.portMax + 1)]
        self.out_fire = [Signal(name=f"io_out_{port}_fire") for port in range(self.portMax + 1)]

    # Elaborate each grouped RealWBArbiter and no-write ready path. / 展开各分组 RealWBArbiter 及无需写回的 ready 路径。
    def elaborate(self, platform) -> Module:
        del platform
        module = Module()
        for port, arbiter in self.arbiters.items():
            module.submodules[f"arb_{port}"] = arbiter
            for slot, index in enumerate(self.inGroup[port]):
                module.d.comb += [
                    arbiter.in_valid[slot].eq(self.in_valid[index]),
                    arbiter.in_bits[slot].eq(self.in_bits[index]),
                    arbiter.in_pdest[slot].eq(self.in_pdest[index]),
                    arbiter.in_rfWen[slot].eq(self.in_rfWen[index]),
                    arbiter.in_fpWen[slot].eq(self.in_fpWen[index]),
                    arbiter.in_vecWen[slot].eq(self.in_vecWen[index]),
                    arbiter.in_v0Wen[slot].eq(self.in_v0Wen[index]),
                    arbiter.in_vlWen[slot].eq(self.in_vlWen[index]),
                    self.in_ready[index].eq(arbiter.in_ready[slot]),
                ]
        for index, port in enumerate(self.inPorts):
            if port < 0 or port not in self.arbiters:
                module.d.comb += self.in_ready[index].eq(1)
        for port in range(self.portMax + 1):
            if port in self.arbiters:
                arbiter = self.arbiters[port]
                module.d.comb += [
                    arbiter.out_ready.eq(1),
                    self.out_valid[port].eq(arbiter.out_valid),
                    self.out_bits[port].eq(arbiter.out_bits),
                    self.out_pdest[port].eq(arbiter.out_pdest),
                    self.out_rfWen[port].eq(arbiter.out_rfWen),
                    self.out_fpWen[port].eq(arbiter.out_fpWen),
                    self.out_vecWen[port].eq(arbiter.out_vecWen),
                    self.out_v0Wen[port].eq(arbiter.out_v0Wen),
                    self.out_vlWen[port].eq(arbiter.out_vlWen),
                    self.out_fire[port].eq(arbiter.out_valid),
                ]
            else:
                module.d.comb += [
                    self.out_valid[port].eq(0),
                    self.out_bits[port].eq(0),
                    self.out_pdest[port].eq(0),
                    self.out_rfWen[port].eq(0),
                    self.out_fpWen[port].eq(0),
                    self.out_vecWen[port].eq(0),
                    self.out_v0Wen[port].eq(0),
                    self.out_vlWen[port].eq(0),
                    self.out_fire[port].eq(0),
                ]
        return module


class WbDataPath(Elaboratable):
    """Compact explicit-configuration V2 write-back data path.
    紧凑且显式配置的 V2 写回数据通路。
    """

    # Construct flattened EXU channels and one checker per register class. / 构造展平 EXU 通道及每类寄存器的一个冲突检查器。
    def __init__(self, config: WbDataPathConfig | dict[str, Any] | None = None,
                 injected_dependencies: Any = None) -> None:
        if config is None:
            self.config = WbDataPathConfig()
        elif isinstance(config, WbDataPathConfig):
            self.config = config
        else:
            self.config = WbDataPathConfig(**dict(config))
        self.injected_dependencies = injected_dependencies
        attrs = self.config.allExus
        self.allExus = attrs
        self.numExu = len(attrs)
        width = self.config.dataWidth
        addr = self.config.addrWidth
        self.flush = Signal(name="io_flush_valid")
        self.fromExu_valid = [Signal(name=f"io_fromExu_{index}_valid") for index in range(self.numExu)]
        self.fromExu_ready = [Signal(name=f"io_fromExu_{index}_ready") for index in range(self.numExu)]
        self.fromExu_bits = [Signal(width, name=f"io_fromExu_{index}_bits_data") for index in range(self.numExu)]
        self.fromExu_pdest = [Signal(addr, name=f"io_fromExu_{index}_bits_pdest") for index in range(self.numExu)]
        self.toIntRf = [Signal(name=f"io_fromExu_{index}_intWen") for index in range(self.numExu)]
        self.toFpRf = [Signal(name=f"io_fromExu_{index}_fpWen") for index in range(self.numExu)]
        self.toVecRf = [Signal(name=f"io_fromExu_{index}_vecWen") for index in range(self.numExu)]
        self.toV0Rf = [Signal(name=f"io_fromExu_{index}_v0Wen") for index in range(self.numExu)]
        self.toVlRf = [Signal(name=f"io_fromExu_{index}_vlWen") for index in range(self.numExu)]
        self.intArb = self.make_checker(self.config.intWbPorts, self.config.intPortMax, attrs, "int")
        self.fpArb = self.make_checker(self.config.fpWbPorts, self.config.fpPortMax, attrs, "fp")
        self.vfArb = self.make_checker(self.config.vfWbPorts, self.config.vfPortMax, attrs, "vf")
        self.v0Arb = self.make_checker(self.config.v0WbPorts, self.config.v0PortMax, attrs, "v0")
        self.vlArb = self.make_checker(self.config.vlWbPorts, self.config.vlPortMax, attrs, "vl")
        self.toIntPreg_valid = self.intArb.out_fire
        self.toIntPreg_bits = self.intArb.out_bits
        self.toIntPreg_pdest = self.intArb.out_pdest
        self.toFpPreg_valid = self.fpArb.out_fire
        self.toFpPreg_bits = self.fpArb.out_bits
        self.toFpPreg_pdest = self.fpArb.out_pdest
        self.toVfPreg_valid = self.vfArb.out_fire
        self.toVfPreg_bits = self.vfArb.out_bits
        self.toVfPreg_pdest = self.vfArb.out_pdest
        self.toV0Preg_valid = self.v0Arb.out_fire
        self.toV0Preg_bits = self.v0Arb.out_bits
        self.toV0Preg_pdest = self.v0Arb.out_pdest
        self.toVlPreg_valid = self.vlArb.out_fire
        self.toVlPreg_bits = self.vlArb.out_bits
        self.toVlPreg_pdest = self.vlArb.out_pdest
        self.toCtrl_writeback_valid = [Signal(name=f"io_toCtrl_{index}_valid") for index in range(self.numExu)]
        self.toCtrl_writeback_bits = [Signal(width, name=f"io_toCtrl_{index}_bits_data") for index in range(self.numExu)]

    # Build one register-class checker from writer attributes and port metadata. / 根据写回属性与端口元数据构造一个寄存器类别检查器。
    def make_checker(
        self,
        ports: Iterable[int],
        port_max: int,
        attrs: tuple[WbExuAttr, ...],
        kind: str,
    ) -> RealWBCollideChecker:
        flag_name = {
            "int": "writeIntRf",
            "fp": "writeFpRf",
            "vf": "writeVfRf",
            "v0": "writeV0Rf",
            "vl": "writeVlRf",
        }[kind]
        writers = [index for index, attr in enumerate(attrs) if getattr(attr, flag_name)]
        mapping = tuple(int(item) for item in ports)
        if not mapping:
            mapping = tuple(range(len(writers)))
        elif len(mapping) == len(attrs):
            mapping = tuple(mapping[index] for index in writers)
        elif len(mapping) < len(writers):
            mapping = mapping + tuple(-1 for _ in range(len(writers) - len(mapping)))
        priorities = tuple(index for index in writers)
        max_port = max(int(port_max), max(mapping, default=0))
        return RealWBCollideChecker(
            self.config.dataWidth,
            mapping,
            range(max_port + 1),
            max_port,
            self.config.addrWidth,
            priorities,
        )

    # Elaborate EXU routing, uncertain-latency backpressure, and ctrl writeback. / 展开 EXU 路由、不确定延迟反压及控制块写回。
    def elaborate(self, platform) -> Module:
        del platform
        module = Module()
        checkers = {
            "int": (self.intArb, self.toIntRf, "writeIntRf"),
            "fp": (self.fpArb, self.toFpRf, "writeFpRf"),
            "vf": (self.vfArb, self.toVecRf, "writeVfRf"),
            "v0": (self.v0Arb, self.toV0Rf, "writeV0Rf"),
            "vl": (self.vlArb, self.toVlRf, "writeVlRf"),
        }
        for name, (checker, flags, _) in checkers.items():
            module.submodules[f"{name}_wb"] = checker
        writer_slots = {
            name: [index for index, attr in enumerate(self.allExus) if getattr(attr, flag)]
            for name, (_, _, flag) in checkers.items()
        }
        # Connect each EXU to the corresponding register-class checker.
        for name, (checker, flags, _) in checkers.items():
            slots = writer_slots[name]
            for slot, exu_index in enumerate(slots):
                module.d.comb += [
                    checker.in_valid[slot].eq(self.fromExu_valid[exu_index] & flags[exu_index]),
                    checker.in_bits[slot].eq(self.fromExu_bits[exu_index]),
                    checker.in_pdest[slot].eq(self.fromExu_pdest[exu_index]),
                    checker.in_rfWen[slot].eq(self.toIntRf[exu_index]),
                    checker.in_fpWen[slot].eq(self.toFpRf[exu_index]),
                    checker.in_vecWen[slot].eq(self.toVecRf[exu_index]),
                    checker.in_v0Wen[slot].eq(self.toV0Rf[exu_index]),
                    checker.in_vlWen[slot].eq(self.toVlRf[exu_index]),
                ]
        # Route ready and control writeback.  A vector EXU's integer writeback
        # is delayed one cycle in V2; retain that boundary explicitly.
        for exu_index, attr in enumerate(self.allExus):
            write_terms: list[Any] = []
            slot_map: dict[str, int] = {}
            for name, slots in writer_slots.items():
                if exu_index in slots:
                    slot_map[name] = slots.index(exu_index)
                    checker = checkers[name][0]
                    flag = checkers[name][1][exu_index]
                    write_terms.append(checker.in_ready[slot_map[name]] & flag)
            no_write = ~(
                self.toIntRf[exu_index]
                | self.toFpRf[exu_index]
                | self.toVecRf[exu_index]
                | self.toV0Rf[exu_index]
                | self.toVlRf[exu_index]
            )
            if attr.hasUncertainLatency:
                ready_expr: Any = no_write
                for term in write_terms:
                    ready_expr = ready_expr | term
                module.d.comb += self.fromExu_ready[exu_index].eq(ready_expr)
            else:
                module.d.comb += self.fromExu_ready[exu_index].eq(1)
            if attr.hasNoDataWB or attr.isHighestWBPriority:
                module.d.comb += self.fromExu_ready[exu_index].eq(1)
            module.d.comb += [
                self.toCtrl_writeback_valid[exu_index].eq(
                    self.fromExu_valid[exu_index] & self.fromExu_ready[exu_index]
                ),
                self.toCtrl_writeback_bits[exu_index].eq(self.fromExu_bits[exu_index]),
            ]
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Export one explicitly selected V2 datapath surface. / 导出显式选择的 V2 数据通路表面。
def build_verilog(configuration, injected_dependencies):
    """Return deterministic Verilog for a configured write-back surface.
    返回配置写回表面的确定性 Verilog。
    """
    from amaranth.back import verilog

    config: dict[str, Any] = configuration if isinstance(configuration, dict) else {}
    del injected_dependencies
    module_name = str(config.get("module", "WbArbiterDispatcher"))
    if module_name == "RealWBArbiter":
        top = RealWBArbiter(
            int(config.get("data_width", config.get("dataWidth", 64))),
            int(config.get("n", 3)),
            int(config.get("addr_width", config.get("addrWidth", 8))),
        )
        ports: list[Any] = [top.out_valid, top.out_bits, top.out_pdest,
                            top.out_rfWen, top.out_fpWen, top.out_vecWen,
                            top.out_v0Wen, top.out_vlWen, top.out_ready,
                            top.chosen]
        ports += top.in_valid + top.in_ready + top.in_bits + top.in_pdest
        ports += top.in_rfWen + top.in_fpWen + top.in_vecWen + top.in_v0Wen + top.in_vlWen
        return verilog.convert(top, name="RealWBArbiter", ports=ports)
    if module_name == "RealWBCollideChecker":
        ports_cfg = tuple(config.get("in_ports", config.get("inPorts", (0, 0, 1))))
        range_cfg = tuple(config.get("port_range", config.get("portRange", range(max(ports_cfg, default=0) + 1))))
        top = RealWBCollideChecker(
            int(config.get("data_width", config.get("dataWidth", 64))),
            ports_cfg,
            range_cfg,
            int(config.get("port_max", config.get("portMax", max(range_cfg, default=0)))),
            int(config.get("addr_width", config.get("addrWidth", 8))),
            config.get("priorities"),
        )
        ports = top.in_valid + top.in_ready + top.in_bits + top.in_pdest
        ports += top.in_rfWen + top.in_fpWen + top.in_vecWen + top.in_v0Wen + top.in_vlWen
        ports += top.out_valid + top.out_bits + top.out_pdest + top.out_rfWen
        ports += top.out_fpWen + top.out_vecWen + top.out_v0Wen + top.out_vlWen
        return verilog.convert(top, name="RealWBCollideChecker", ports=ports)
    if module_name == "WbDataPath":
        cfg = config.get("config", config)
        top = WbDataPath(cfg if isinstance(cfg, WbDataPathConfig) else WbDataPathConfig(**{
            key: value for key, value in cfg.items()
            if key in WbDataPathConfig.__dataclass_fields__
        }))
        ports = [top.flush] + top.fromExu_valid + top.fromExu_ready + top.fromExu_bits + top.fromExu_pdest
        ports += top.toIntRf + top.toFpRf + top.toVecRf + top.toV0Rf + top.toVlRf
        for valid, bits, pdest in (
                (top.toIntPreg_valid, top.toIntPreg_bits, top.toIntPreg_pdest),
                (top.toFpPreg_valid, top.toFpPreg_bits, top.toFpPreg_pdest),
                (top.toVfPreg_valid, top.toVfPreg_bits, top.toVfPreg_pdest),
                (top.toV0Preg_valid, top.toV0Preg_bits, top.toV0Preg_pdest),
                (top.toVlPreg_valid, top.toVlPreg_bits, top.toVlPreg_pdest)):
            ports += list(valid) + list(bits) + list(pdest)
        ports += top.toCtrl_writeback_valid + top.toCtrl_writeback_bits
        return verilog.convert(top, name="WbDataPath", ports=ports)
    top = WbArbiterDispatcher(
        int(config.get("data_width", config.get("dataWidth", 64))),
        int(config.get("n", 5)),
    )
    ports = [top.in_valid, top.in_ready, top.in_bits, top.notWrite]
    ports += top.acceptVec + top.out_valid + top.out_ready + top.out_bits
    return verilog.convert(top, name="WbArbiterDispatcher", ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default dispatcher export. / 打印默认分发器导出结果。
def main() -> None:
    print(build_verilog(None, None))


if __name__ == "__main__":
    main()
