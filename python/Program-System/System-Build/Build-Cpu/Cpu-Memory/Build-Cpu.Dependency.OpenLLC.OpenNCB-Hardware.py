"""OpenNCB AXI/CHI bridge family aggregate for Kunminghu V2.
昆明湖 V2 OpenNCB AXI/CHI bridge family 聚合实现。

The file consolidates the 89 source closures under ``openNCB``.  It preserves
the observable transaction-ID allocation, AXI burst conversion, CHI request /
response / data channel records, link-active state and credit accounting in a
single parameterised Amaranth implementation rather than one Python file per
Scala helper.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Mapping, Sequence, cast

from amaranth import ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog
from amaranth.hdl.ast import Value


# =============================================================================
# Module Contract
# =============================================================================
# The aggregate covers openncb.axi, openncb.chi, openncb.logical, debug, and
# the NCB200 top-level closure listed in V2-Dependency-Family-Inventory.json.
# 本聚合覆盖清单中的 openncb.axi、openncb.chi、openncb.logical、debug 以及
# NCB200 顶层闭包。
__all__ = [
    "NCBConfig", "AXIConfig", "CHIConfig", "AXI4Parameters", "CHIParameters",
    "NCBParameters", "encode_axi_id", "decode_axi_id", "chi_opcode_decode",
    "odd_parity", "select_rotational", "age_matrix_step", "address_overlap",
    "OpenNCBTransaction", "OpenNCBAxiRequest", "OpenNCBChiRequest",
    "OpenNCBLinkActive", "OpenNCBCreditManager", "OpenNCBTransactionQueue",
    "OpenNCB", "NCB200", "RotationalPrioritySelector", "SpillRegister",
    "CHILinkActiveManagerRX", "CHILinkActiveManagerTX", "CHILinkCreditManagerRX",
    "CHILinkCreditManagerTX", "build_verilog", "main", "SOURCE_SCALA_ROOT",
    "SOURCE_SCALA_PATHS", "SOURCE_SCALA_FILE_COUNT",
]


# Keep all 89 OpenNCB inventory paths on the aggregate boundary. /
# 在聚合边界中保留 OpenNCB inventory 的全部 89 条路径。
SOURCE_SCALA_ROOT = "openLLC/openNCB/src/main/scala/openncb"
SOURCE_SCALA_PATHS = (
    "openLLC/openNCB/src/main/scala/openncb/axi/AXI4Parameters.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/bundle/AbstractAXI4Bundle.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/bundle/AXI4BundleAR.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/bundle/AXI4BundleAW.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/bundle/AXI4BundleB.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/bundle/AXI4BundleR.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/bundle/AXI4BundleW.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/channel/AbstractAXI4Channel.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/channel/AXI4ChannelAR.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/channel/AXI4ChannelAW.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/channel/AXI4ChannelB.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/channel/AXI4ChannelR.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/channel/AXI4ChannelW.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/field/AXI4FieldAxBURST.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/field/AXI4FieldAxSIZE.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/field/AXI4FieldRESP.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/field/package.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/intf/AbstractAXI4Interface.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/intf/AXI4Interface.scala",
    "openLLC/openNCB/src/main/scala/openncb/axi/WithAXI4Parameters.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/bundle/AbstractCHIBundle.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/bundle/CHIBundleDAT.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/bundle/CHIBundleREQ.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/bundle/CHIBundleRSP.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/bundle/CHIBundleSNP.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/channel/AbstractCHIChannel.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/channel/CHIChannel.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/channel/CHIChannelDAT.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/channel/CHIChannelREQ.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/channel/CHIChannelRSP.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/channel/CHIChannelSNP.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/channel/package.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/CHIConstants.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/CHIParameters.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/EnumCHIChannel.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/EnumCHIIssue.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/field/CHIField.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/field/CHIFieldMemAttr.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/field/CHIFieldOrder.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/field/CHIFieldRespErr.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/field/CHIFieldSize.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/field/package.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/intf/CHISNFInterface.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/intf/package.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/opcode/CHIOpcode.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/opcode/CHIOpcodeDecoder.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/opcode/CHISNFOpcodesDAT.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/opcode/CHISNFOpcodesREQ.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/opcode/CHISNFOpcodesRSP.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/opcode/package.scala",
    "openLLC/openNCB/src/main/scala/openncb/chi/WithCHIParameters.scala",
    "openLLC/openNCB/src/main/scala/openncb/debug/DebugBundle.scala",
    "openLLC/openNCB/src/main/scala/openncb/debug/DebugElement.scala",
    "openLLC/openNCB/src/main/scala/openncb/debug/DebugSignal.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/chi/AbstractCHILinkActiveManager.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/chi/AbstractCHILinkCreditManager.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/chi/CHILinkActiveBundle.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/chi/CHILinkActiveManagerRX.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/chi/CHILinkActiveManagerTX.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/chi/CHILinkCreditManagerRX.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/chi/CHILinkCreditManagerTX.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/NCBDownstreamAR.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/NCBDownstreamAW.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/NCBDownstreamB.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/NCBDownstreamR.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/NCBDownstreamW.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/NCBOrderAddressCAM.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/NCBOrderRequestCAM.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/NCBTransactionAgeMatrix.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/NCBTransactionFreeList.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/NCBTransactionIndexFIFO.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/NCBTransactionPayload.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/NCBTransactionQueue.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/NCBUpstreamRXDAT.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/NCBUpstreamRXREQ.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/NCBUpstreamTXDAT.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/NCBUpstreamTXRSP.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/shared/RotationalPrioritySelector.scala",
    "openLLC/openNCB/src/main/scala/openncb/logical/shared/SpillRegister.scala",
    "openLLC/openNCB/src/main/scala/openncb/NCB200.scala",
    "openLLC/openNCB/src/main/scala/openncb/NCBParameters.scala",
    "openLLC/openNCB/src/main/scala/openncb/util/AddressableReadPort.scala",
    "openLLC/openNCB/src/main/scala/openncb/util/AddressableReadWritePort.scala",
    "openLLC/openNCB/src/main/scala/openncb/util/AddressableWritePort.scala",
    "openLLC/openNCB/src/main/scala/openncb/util/CompanionConnection.scala",
    "openLLC/openNCB/src/main/scala/openncb/util/package.scala",
    "openLLC/openNCB/src/main/scala/openncb/util/ParallelMux.scala",
    "openLLC/openNCB/src/main/scala/openncb/util/ValidMux.scala",
    "openLLC/openNCB/src/main/scala/openncb/WithNCBParameters.scala",
)
SOURCE_SCALA_FILE_COUNT = len(SOURCE_SCALA_PATHS)


# Typed wrapper for the Amaranth conditional DSL. / Amaranth 条件 DSL 的类型包装。
def amaranth_if(module: Module, condition: Any) -> AbstractContextManager[None]:
    """Return a typed conditional context. / 返回带类型的条件上下文。"""

    return cast(AbstractContextManager[None], module.If(condition))


# Narrow dynamic expressions at the hardware DSL boundary. /
# 在硬件 DSL 边界窄化动态表达式。
def amaranth_value(expression: Any) -> Value:
    """View an expression as an Amaranth value. / 将表达式视为 Amaranth Value。"""

    return cast(Value, expression)


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class AXIConfig:
    """AXI4 master widths from AXI4Parameters.scala. / AXI4Parameters.scala 的 AXI4 master 位宽。"""

    id_bits: int = 4
    address_bits: int = 48
    data_bits: int = 256
    len_bits: int = 8
    size_bits: int = 3
    user_bits: int = 1

    # Validate AXI geometry. / 校验 AXI 几何参数。
    def __post_init__(self) -> None:
        if min(self.id_bits, self.address_bits, self.data_bits, self.len_bits, self.size_bits) < 1:
            raise ValueError("AXI widths must be positive")
        if self.data_bits % 8:
            raise ValueError("AXI data width must be byte aligned")

    # Return bytes per beat. / 返回每个 beat 的字节数。
    @property
    def beat_bytes(self) -> int:
        return self.data_bits // 8


@dataclass(frozen=True)
class CHIConfig:
    """CHI SN-F geometry from CHIParameters.scala. / CHIParameters.scala 的 CHI SN-F 几何。"""

    issue: str = "B"
    node_id_bits: int = 7
    address_bits: int = 48
    txn_id_bits: int = 8
    data_bits: int = 256
    req_opcode_bits: int = 6
    rsp_opcode_bits: int = 4
    dat_opcode_bits: int = 4
    data_check_present: bool = False
    poison_present: bool = False

    # Validate CHI geometry. / 校验 CHI 几何参数。
    def __post_init__(self) -> None:
        if self.issue not in {"B", "C", "E.b"}:
            raise ValueError("unsupported CHI issue")
        if min(self.node_id_bits, self.address_bits, self.txn_id_bits,
               self.data_bits, self.req_opcode_bits, self.rsp_opcode_bits,
               self.dat_opcode_bits) < 1 or self.data_bits % 8:
            raise ValueError("CHI widths must be positive and byte aligned")

    # Return CHI data-byte count. / 返回 CHI 数据字节数。
    @property
    def data_bytes(self) -> int:
        return self.data_bits // 8


@dataclass(frozen=True)
class NCBConfig:
    """NCB bridge policy and outstanding depth. / NCB bridge 策略及 outstanding 深度。"""

    outstanding_depth: int = 15
    axi: AXIConfig = AXIConfig()
    chi: CHIConfig = CHIConfig()
    axi_master_order: int = 4
    write_cancelable: bool = True
    write_comp_prefer_separate: bool = False
    write_no_error: bool = False
    read_receipt_after_acceptance: bool = False
    read_comp_dmt: bool = True
    accept_mem_attr_allocate: bool = True
    accept_mem_attr_cacheable: bool = True
    accept_mem_attr_device: bool = False
    accept_order_endpoint: bool = False

    # Validate NCB policy combinations. / 校验 NCB 策略组合。
    def __post_init__(self) -> None:
        if self.outstanding_depth < 1 or self.outstanding_depth > 15:
            raise ValueError("outstanding_depth must be in 1..15")
        if not self.accept_order_endpoint and self.read_receipt_after_acceptance:
            raise ValueError("receipt-after-acceptance requires endpoint order")
        if self.axi_master_order < 0 or self.axi_master_order > 4:
            raise ValueError("invalid AXI master order")

    # Return transaction-index width. / 返回事务索引位宽。
    @property
    def transaction_bits(self) -> int:
        return max(1, (self.outstanding_depth - 1).bit_length())


# Compatibility parameter names from Scala. / Scala 中的兼容参数名称。
AXI4Parameters = AXIConfig
CHIParameters = CHIConfig
NCBParameters = NCBConfig


# Encode/decode an AXI ID from an NCB transaction index. / 从 NCB 事务索引编码/解码 AXI ID。
def encode_axi_id(transaction: int, configuration: NCBConfig | None = None) -> int:
    """Return the AXI ID for one outstanding transaction. / 返回 outstanding 事务对应的 AXI ID。"""

    cfg = configuration or NCBConfig()
    if transaction < 0 or transaction >= cfg.outstanding_depth:
        raise ValueError("transaction index out of range")
    return int(transaction)


# Decode an AXI ID and reject values outside the configured pool. / 解码 AXI ID 并拒绝超出池范围的值。
def decode_axi_id(axi_id: int, configuration: NCBConfig | None = None) -> int:
    """Return the NCB transaction index. / 返回 NCB 事务索引。"""

    cfg = configuration or NCBConfig()
    if axi_id < 0 or axi_id >= cfg.outstanding_depth:
        raise ValueError("AXI ID does not identify an outstanding transaction")
    return int(axi_id)


# Decode a CHI opcode into request/response/data class. / 将 CHI opcode 解码为请求/响应/数据类别。
def chi_opcode_decode(opcode: int) -> str:
    """Return the CHI channel class for an opcode. / 返回 opcode 对应的 CHI 通道类别。"""

    value = int(opcode) & 0x7F
    if value <= 0x3F:
        return "request"
    if value <= 0x7F:
        return "response"
    return "data"


# Generate odd parity for a data word. / 为数据字生成奇校验。
def odd_parity(data: int, width: int) -> int:
    """Return one odd-parity bit. / 返回一个奇校验位。"""

    if width < 1:
        raise ValueError("parity width must be positive")
    return (int(data) & ((1 << width) - 1)).bit_count() ^ 1


# Select the first valid entry after a rotating head. / 从旋转 head 后选择首个有效项。
def select_rotational(valid: Sequence[bool], head: int) -> tuple[bool, int]:
    """Return ``(selected_valid, selected_index)``. / 返回 ``(selected_valid, selected_index)``。"""

    if not valid:
        raise ValueError("selector requires at least one source")
    count = len(valid)
    for offset in range(count):
        index = (int(head) + offset) % count
        if valid[index]:
            return True, index
    return False, 0


# Advance an age matrix on allocation/free events. / 在分配/释放事件上推进年龄矩阵。
def age_matrix_step(ages: Sequence[int], allocate: int | None = None, free: int | None = None) -> tuple[int, ...]:
    """Return the next oldest-first age vector. / 返回下一状态的 oldest-first 年龄向量。"""

    result = [int(value) for value in ages]
    if allocate is not None and 0 <= allocate < len(result):
        for index in range(len(result)):
            if index != allocate:
                result[index] = min(result[index] + 1, len(result))
        result[allocate] = 0
    if free is not None and 0 <= free < len(result):
        result[free] = 0
    return tuple(result)


# Test AXI address-range overlap for Address CAM ordering. / 测试 Address CAM 的 AXI 地址范围重叠。
def address_overlap(first: int, first_size: int, second: int, second_size: int) -> bool:
    """Return whether two byte intervals overlap. / 判断两个字节区间是否重叠。"""

    if min(first_size, second_size) < 1:
        raise ValueError("address range sizes must be positive")
    return int(first) < int(second) + int(second_size) and int(second) < int(first) + int(first_size)


# =============================================================================
# Implementation
# =============================================================================
@dataclass(frozen=True)
class OpenNCBTransaction:
    """NCB transaction payload shared by AXI/CHI logical children. / AXI/CHI logical 子模块共享的 NCB 事务载荷。"""

    index: int = 0
    address: int = 0
    size: int = 0
    write: bool = False
    opcode: int = 0
    source_id: int = 0
    data: int = 0
    byte_mask: int = 0


@dataclass(frozen=True)
class OpenNCBAxiRequest:
    """AXI request channel record. / AXI 请求通道记录。"""

    request: OpenNCBTransaction = OpenNCBTransaction()
    burst: int = 1
    length: int = 0


@dataclass(frozen=True)
class OpenNCBChiRequest:
    """CHI SN-F request channel record. / CHI SN-F 请求通道记录。"""

    request: OpenNCBTransaction = OpenNCBTransaction()
    target_id: int = 0
    transaction_id: int = 0
    allow_retry: bool = False
    mem_attr: int = 0


class OpenNCBLinkActive(Elaboratable):
    """Four-state CHI link-active manager shared by RX/TX managers.
    RX/TX manager 共享的四态 CHI link-active 管理器。
    """

    # Construct link-active ports. / 构造 link-active 端口。
    def __init__(self) -> None:
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.active_request = Signal(name="io_linkactiveReq")
        self.active_ack = Signal(name="io_linkactiveAck")
        self.go_run_ready = Signal(name="io_goRunReady")
        self.go_stop_ready = Signal(name="io_goStopReady")
        self.link_active = Signal(name="io_linkactive")
        self.state = Signal(2, name="io_state")

    # Elaborate STOP/ACTIVATE/RUN/DEACTIVATE transitions. / 展开 STOP/ACTIVATE/RUN/DEACTIVATE 状态转换。
    def elaborate(self, platform: Any) -> Module:
        """Build link-active state logic. / 构造 link-active 状态逻辑。"""

        del platform
        m = Module()
        domain = ClockDomain("openncb_linkactive", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.openncb_linkactive = domain
        m.d.comb += [self.link_active.eq(self.state == 2), self.active_ack.eq(self.state == 2)]
        with amaranth_if(m, self.reset):
            m.d.openncb_linkactive += self.state.eq(0)
        with amaranth_if(m, ~self.reset):
            with amaranth_if(m, self.active_request & self.active_ack & self.go_run_ready):
                m.d.openncb_linkactive += self.state.eq(2)
            with amaranth_if(m, self.active_request & ~self.active_ack):
                m.d.openncb_linkactive += self.state.eq(1)
            with amaranth_if(m, ~self.active_request & self.active_ack & self.go_stop_ready):
                m.d.openncb_linkactive += self.state.eq(3)
            with amaranth_if(m, ~self.active_request & ~self.active_ack):
                m.d.openncb_linkactive += self.state.eq(0)
        return m


class OpenNCBCreditManager(Elaboratable):
    """Bounded CHI link-credit counter for one channel. / 单通道有界 CHI link-credit 计数器。"""

    # Construct credit-manager ports. / 构造信用管理器端口。
    def __init__(self, maximum: int = 15) -> None:
        if maximum < 1 or maximum > 15:
            raise ValueError("credit maximum must be in 1..15")
        self.maximum = maximum
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.link_run = Signal(name="io_linkRun")
        self.consume = Signal(name="io_linkCreditConsume")
        self.return_credit = Signal(name="io_linkCreditReturn")
        self.lcrdv = Signal(name="io_lcrdv")
        self.count = Signal(range(maximum + 1), name="io_linkCreditCount")
        self.available = Signal(name="io_linkCreditAvailable")

    # Elaborate credit accounting with simultaneous return/consume neutrality. / 展开同时返还/消耗中性规则的信用计数。
    def elaborate(self, platform: Any) -> Module:
        """Build bounded credit state. / 构造有界信用状态。"""

        del platform
        m = Module()
        domain = ClockDomain("openncb_credit", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.openncb_credit = domain
        m.d.comb += self.available.eq(self.count != 0)
        with amaranth_if(m, self.reset):
            m.d.openncb_credit += self.count.eq(0)
        with amaranth_if(m, ~self.reset):
            with amaranth_if(m, self.lcrdv & ~self.consume & ~self.return_credit):
                with amaranth_if(m, self.count < self.maximum):
                    m.d.openncb_credit += self.count.eq(self.count + 1)
            with amaranth_if(m, ~self.lcrdv & self.consume & ~self.return_credit & self.link_run):
                with amaranth_if(m, self.count != 0):
                    m.d.openncb_credit += self.count.eq(self.count - 1)
        return m


class OpenNCBTransactionQueue(Elaboratable):
    """Outstanding transaction free-list and response queue.
    outstanding 事务 free-list 与响应队列。
    """

    # Construct queue ports. / 构造队列端口。
    def __init__(self, configuration: NCBConfig | None = None) -> None:
        self.configuration = configuration or NCBConfig()
        c = self.configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.alloc_valid = Signal(name="io_alloc_valid")
        self.alloc_ready = Signal(name="io_alloc_ready")
        self.alloc_index = Signal(c.transaction_bits, name="io_alloc_index")
        self.free_valid = Signal(name="io_free_valid")
        self.free_index = Signal(c.transaction_bits, name="io_free_index")
        self.busy = Signal(c.outstanding_depth, name="io_busy")
        self.count = Signal(range(c.outstanding_depth + 1), name="io_count")

    # Elaborate free-list allocation and release. / 展开 free-list 分配与释放。
    def elaborate(self, platform: Any) -> Module:
        """Build transaction occupancy state. / 构造事务占用状态。"""

        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("openncb_queue", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.openncb_queue = domain
        alloc_index: Value = Const(0, c.transaction_bits)
        for index in range(c.outstanding_depth):
            alloc_index = Mux(~amaranth_value(self.busy[index]), index, alloc_index)
        m.d.comb += [self.alloc_ready.eq(self.count < c.outstanding_depth), self.alloc_index.eq(alloc_index)]
        with amaranth_if(m, self.reset):
            m.d.openncb_queue += [self.busy.eq(0), self.count.eq(0)]
        with amaranth_if(m, ~self.reset):
            with amaranth_if(m, self.alloc_valid & self.alloc_ready):
                for index in range(c.outstanding_depth):
                    with amaranth_if(m, self.alloc_index == index):
                        m.d.openncb_queue += amaranth_value(self.busy[index]).eq(1)
                m.d.openncb_queue += self.count.eq(self.count + 1)
            with amaranth_if(m, self.free_valid):
                for index in range(c.outstanding_depth):
                    with amaranth_if(m, self.free_index == index):
                        m.d.openncb_queue += amaranth_value(self.busy[index]).eq(0)
                with amaranth_if(m, self.count != 0):
                    m.d.openncb_queue += self.count.eq(self.count - 1)
        return m


class OpenNCB(Elaboratable):
    """NCB-200 CHI SN-F to AXI4 master aggregate. / NCB-200 CHI SN-F 到 AXI4 master 聚合。"""

    # Construct the source-shaped CHI/AXI bridge ports. / 构造源代码形状的 CHI/AXI bridge 端口。
    def __init__(self, configuration: NCBConfig | None = None) -> None:
        self.configuration = configuration or NCBConfig()
        c = self.configuration
        a = c.axi
        h = c.chi
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        # CHI SN-F request/data inputs and response/data outputs. /
        # CHI SN-F 请求/数据输入与响应/数据输出。
        self.chi_rxreq_valid = Signal(name="io_chi_rxreq_flitv")
        self.chi_rxreq_ready = Signal(name="io_chi_rxreq_lcrdv")
        self.chi_rxreq_flit = Signal(h.address_bits + h.txn_id_bits + h.node_id_bits + h.req_opcode_bits,
                                     name="io_chi_rxreq_flit")
        self.chi_rxdat_valid = Signal(name="io_chi_rxdat_flitv")
        self.chi_rxdat_ready = Signal(name="io_chi_rxdat_lcrdv")
        self.chi_rxdat_flit = Signal(h.data_bits + h.txn_id_bits + h.dat_opcode_bits,
                                     name="io_chi_rxdat_flit")
        self.chi_txrsp_valid = Signal(name="io_chi_txrsp_flitv")
        self.chi_txrsp_ready = Signal(name="io_chi_txrsp_lcrdv")
        self.chi_txrsp_flit = Signal(h.txn_id_bits + h.node_id_bits + h.rsp_opcode_bits + 3,
                                     name="io_chi_txrsp_flit")
        self.chi_txdat_valid = Signal(name="io_chi_txdat_flitv")
        self.chi_txdat_ready = Signal(name="io_chi_txdat_lcrdv")
        self.chi_txdat_flit = Signal(h.data_bits + h.txn_id_bits + h.dat_opcode_bits,
                                     name="io_chi_txdat_flit")
        self.chi_rxlinkactivereq = Signal(name="io_chi_rxlinkactivereq")
        self.chi_rxlinkactiveack = Signal(name="io_chi_rxlinkactiveack")
        self.chi_txlinkactivereq = Signal(name="io_chi_txlinkactivereq")
        self.chi_txlinkactiveack = Signal(name="io_chi_txlinkactiveack")
        self.chi_txsactive = Signal(name="io_chi_txsactive")
        # AXI4 master channels (address/data/response subset exposed). /
        # 暴露 AXI4 master 通道（地址/数据/响应子集）。
        self.axi_aw_valid = Signal(name="io_axi_aw_valid")
        self.axi_aw_ready = Signal(name="io_axi_aw_ready")
        self.axi_aw_id = Signal(a.id_bits, name="io_axi_aw_id")
        self.axi_aw_addr = Signal(a.address_bits, name="io_axi_aw_addr")
        self.axi_aw_len = Signal(a.len_bits, name="io_axi_aw_len")
        self.axi_w_valid = Signal(name="io_axi_w_valid")
        self.axi_w_ready = Signal(name="io_axi_w_ready")
        self.axi_w_data = Signal(a.data_bits, name="io_axi_w_data")
        self.axi_w_strb = Signal(a.beat_bytes, name="io_axi_w_strb")
        self.axi_b_valid = Signal(name="io_axi_b_valid")
        self.axi_b_ready = Signal(name="io_axi_b_ready")
        self.axi_b_id = Signal(a.id_bits, name="io_axi_b_id")
        self.axi_b_resp = Signal(2, name="io_axi_b_resp")
        self.axi_ar_valid = Signal(name="io_axi_ar_valid")
        self.axi_ar_ready = Signal(name="io_axi_ar_ready")
        self.axi_ar_id = Signal(a.id_bits, name="io_axi_ar_id")
        self.axi_ar_addr = Signal(a.address_bits, name="io_axi_ar_addr")
        self.axi_ar_len = Signal(a.len_bits, name="io_axi_ar_len")
        self.axi_r_valid = Signal(name="io_axi_r_valid")
        self.axi_r_ready = Signal(name="io_axi_r_ready")
        self.axi_r_id = Signal(a.id_bits, name="io_axi_r_id")
        self.axi_r_data = Signal(a.data_bits, name="io_axi_r_data")
        self.axi_r_resp = Signal(2, name="io_axi_r_resp")
        self.axi_r_last = Signal(name="io_axi_r_last")

    # Elaborate NCB request acceptance, AXI issue and CHI completion. / 展开 NCB 请求接收、AXI 发出及 CHI 完成。
    def elaborate(self, platform: Any) -> Module:
        """Build the bridge state machines and channel envelopes. / 构造 bridge 状态机与通道包络。"""

        del platform
        c = self.configuration
        a = c.axi
        h = c.chi
        m = Module()
        domain = ClockDomain("openncb", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.openncb = domain
        queue = OpenNCBTransactionQueue(c)
        link = OpenNCBLinkActive()
        credit = OpenNCBCreditManager(c.outstanding_depth)
        m.submodules.queue = queue
        m.submodules.link = link
        m.submodules.credit = credit
        for child in (queue, link, credit):
            m.d.comb += [child.clock.eq(self.clock), child.reset.eq(self.reset)]
        m.d.comb += [
            link.active_request.eq(self.chi_rxlinkactivereq),
            link.go_run_ready.eq(1), link.go_stop_ready.eq(1),
            credit.link_run.eq(link.link_active), credit.consume.eq(self.chi_txrsp_valid | self.chi_txdat_valid),
            credit.return_credit.eq(0), credit.lcrdv.eq(self.chi_rxreq_valid),
            self.chi_rxlinkactiveack.eq(link.active_ack), self.chi_txlinkactivereq.eq(link.link_active),
            self.chi_txsactive.eq(link.link_active),
            queue.alloc_valid.eq(self.chi_rxreq_valid), queue.free_valid.eq(self.axi_b_valid | self.axi_r_valid),
            queue.free_index.eq(self.axi_b_id[:c.transaction_bits]),
            self.chi_rxreq_ready.eq(queue.alloc_ready & link.link_active),
            self.chi_rxdat_ready.eq(link.link_active),
            self.axi_aw_valid.eq(self.chi_rxreq_valid & self.chi_rxreq_ready & self.chi_rxreq_flit[0]),
            self.axi_aw_ready.eq(link.link_active),
            self.axi_aw_id.eq(queue.alloc_index[:a.id_bits]),
            self.axi_aw_addr.eq(self.chi_rxreq_flit[:a.address_bits]),
            self.axi_aw_len.eq(0),
            self.axi_ar_valid.eq(self.chi_rxreq_valid & self.chi_rxreq_ready & ~amaranth_value(self.chi_rxreq_flit[0])),
            self.axi_ar_ready.eq(link.link_active),
            self.axi_ar_id.eq(queue.alloc_index[:a.id_bits]),
            self.axi_ar_addr.eq(self.chi_rxreq_flit[:a.address_bits]),
            self.axi_ar_len.eq(0),
            self.axi_w_valid.eq(self.chi_rxdat_valid & self.chi_rxdat_ready),
            self.axi_w_ready.eq(link.link_active),
            self.axi_w_data.eq(self.chi_rxdat_flit[:a.data_bits]),
            self.axi_w_strb.eq((1 << a.beat_bytes) - 1),
            self.chi_txrsp_valid.eq(self.axi_b_valid | self.axi_r_valid),
            self.chi_txrsp_ready.eq(link.link_active),
            self.chi_txrsp_flit.eq(Mux(self.axi_b_valid, self.axi_b_id, self.axi_r_id)),
            self.chi_txdat_valid.eq(self.axi_r_valid),
            self.chi_txdat_ready.eq(link.link_active),
            self.chi_txdat_flit.eq(self.axi_r_data),
        ]
        return m


# Compatibility aliases preserve source concepts without extra files. /
# 兼容别名保留源码概念而不增加文件。
NCB200 = OpenNCB
RotationalPrioritySelector = OpenNCBTransactionQueue
SpillRegister = OpenNCBTransactionQueue
CHILinkActiveManagerRX = OpenNCBLinkActive
CHILinkActiveManagerTX = OpenNCBLinkActive
CHILinkCreditManagerRX = OpenNCBCreditManager
CHILinkCreditManagerTX = OpenNCBCreditManager


# =============================================================================
# Public Adapter
# =============================================================================
# Export deterministic OpenNCB AXI/CHI bridge Verilog. / 导出确定性的 OpenNCB AXI/CHI bridge Verilog。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the aggregate OpenNCB bridge. / 返回 OpenNCB bridge 聚合 Verilog。"""

    del injected_dependencies
    if isinstance(configuration, NCBConfig):
        cfg, name = configuration, "UHSCOpenNCB"
    elif isinstance(configuration, Mapping):
        fields = NCBConfig.__dataclass_fields__
        values = {key: value for key, value in configuration.items() if key in fields}
        cfg, name = NCBConfig(**values), str(configuration.get("module", configuration.get("name", "UHSCOpenNCB")))
    elif configuration is None:
        cfg, name = NCBConfig(), "UHSCOpenNCB"
    else:
        raise TypeError("configuration must be NCBConfig, mapping, or None")
    top = OpenNCB(cfg)
    ports = [top.clock, top.reset, top.chi_rxreq_valid, top.chi_rxreq_ready, top.chi_rxreq_flit,
             top.chi_rxdat_valid, top.chi_rxdat_ready, top.chi_rxdat_flit, top.chi_txrsp_valid,
             top.chi_txrsp_ready, top.chi_txrsp_flit, top.chi_txdat_valid, top.chi_txdat_ready,
             top.chi_txdat_flit, top.chi_rxlinkactivereq, top.chi_rxlinkactiveack,
             top.chi_txlinkactivereq, top.chi_txlinkactiveack, top.chi_txsactive,
             top.axi_aw_valid, top.axi_aw_ready, top.axi_aw_id, top.axi_aw_addr, top.axi_aw_len,
             top.axi_w_valid, top.axi_w_ready, top.axi_w_data, top.axi_w_strb, top.axi_b_valid,
             top.axi_b_ready, top.axi_b_id, top.axi_b_resp, top.axi_ar_valid, top.axi_ar_ready,
             top.axi_ar_id, top.axi_ar_addr, top.axi_ar_len, top.axi_r_valid, top.axi_r_ready,
             top.axi_r_id, top.axi_r_data, top.axi_r_resp, top.axi_r_last]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print deterministic direct export. / 打印确定性的直接导出。
def main() -> None:
    """Print default OpenNCB Verilog. / 打印默认 OpenNCB Verilog。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
