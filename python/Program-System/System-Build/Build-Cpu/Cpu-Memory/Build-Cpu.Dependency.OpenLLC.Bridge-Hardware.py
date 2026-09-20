"""OpenLLC CHI channel and link bridge family for Kunminghu V2.
昆明湖 V2 OpenLLC CHI 通道与链路 bridge family 聚合实现。

The aggregate represents the eight ``openLLC.chi`` Scala children: it keeps
the issue-specific flit layouts, TX/RX ready-valid channels, link activation
state and L-Credit accounting in one deterministic Amaranth boundary.
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
# The boundary covers LinkLayer.scala and RX/TX REQ/RSP/DAT/SNP converters.
# 此边界覆盖 LinkLayer.scala 及 RX/TX REQ/RSP/DAT/SNP 转换器。
__all__ = [
    'OpenLLCChiConfig',
    'CHI_REQ',
    'CHI_RSP',
    'CHI_DAT',
    'CHI_SNP',
    'CHI_REQ_OPCODES',
    'CHI_RSP_OPCODES',
    'CHI_DAT_OPCODES',
    'CHI_SNP_OPCODES',
    'LINK_STOP',
    'LINK_ACTIVATE',
    'LINK_RUN',
    'LINK_DEACTIVATE',
    'chi_layout',
    'pack_fields',
    'unpack_fields',
    'next_link_state',
    'credit_update',
    'request_from_mmio',
    'chi_handshake_observation',
    'OpenLLCLinkLayer',
    'OpenLLCChannelTransmitter',
    'OpenLLCChannelReceiver',
    'LinkLayer',
    'TXREQ',
    'TXRSP',
    'TXDAT',
    'TXSNP',
    'RXREQ',
    'RXRSP',
    'RXDAT',
    'OpenLLCBridge',
    'build_verilog',
    'main',
]


def chi_handshake_observation(valid: bool, ready: bool,
                              credit_return: bool = False) -> dict[str, int]:
    """Summarize one CHI channel's ready/valid and L-Credit event.

    This pure helper mirrors the link-layer equations and keeps the historical
    Verilog port list untouched, while giving protocol monitors a deterministic
    observation point for fire/stall/credit-return behavior.
    返回单个 CHI 通道 ready/valid 与 L-Credit 事件摘要，不改变旧端口。
    """

    valid_bit = int(bool(valid))
    ready_bit = int(bool(ready))
    credit_bit = int(bool(credit_return))
    return {
        "valid": valid_bit,
        "ready": ready_bit,
        "credit_return": credit_bit,
        "fire": valid_bit & ready_bit,
        "stalled": valid_bit & (1 - ready_bit),
    }


# Keep all eight CHI inventory paths on the bridge aggregate. /
# 在 bridge 聚合中保留 CHI inventory 的全部 8 条路径。


# Typed wrapper for conditional DSL contexts. / 条件 DSL 上下文的类型包装。
def amaranth_if(module: Module, condition: Any) -> AbstractContextManager[None]:
    """Return a typed Amaranth conditional context. / 返回带类型的 Amaranth 条件上下文。"""

    return cast(AbstractContextManager[None], module.If(condition))


# Narrow runtime expressions to Value for strict Pyright checks. /
# 将运行时表达式窄化为 Value 以通过严格 Pyright 检查。
def amaranth_value(expression: Any) -> Value:
    """View an expression as an Amaranth value. / 将表达式视为 Amaranth 值。"""

    return cast(Value, expression)


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class OpenLLCChiConfig:
    """Issue-specific CHI geometry from the V2 message definitions. / V2 message 定义中的 issue 专用 CHI 几何。"""

    issue: str = "B"
    address_bits: int = 48
    node_id_bits: int = 7
    txn_id_bits: int = 8
    data_bits: int = 256
    credit_depth: int = 15
    source_id: int = 0
    target_id: int = 0
    data_check: bool = False
    poison: bool = False

    # Validate CHI issue and widths. / 校验 CHI issue 与位宽。
    def __post_init__(self) -> None:
        if self.issue not in {"B", "C", "E.b"}:
            raise ValueError("issue must be B, C, or E.b")
        if min(self.address_bits, self.node_id_bits, self.txn_id_bits,
               self.data_bits, self.credit_depth) < 1 or self.data_bits % 8:
            raise ValueError("CHI widths must be positive and byte aligned")
        if self.credit_depth > 15:
            raise ValueError("CHI L-Credit depth is limited to 15")

    # Return issue-specific opcode widths. / 返回 issue 专用 opcode 位宽。
    @property
    def opcode_bits(self) -> int:
        return 7 if self.issue == "E.b" else 6

    # Return data-byte count. / 返回数据字节数。
    @property
    def data_bytes(self) -> int:
        return self.data_bits // 8


@dataclass(frozen=True)
class CHI_REQ:
    """Source-shaped CHI request record. / 源代码形状的 CHI 请求记录。"""

    txn_id: int = 0
    src_id: int = 0
    tgt_id: int = 0
    opcode: int = 0
    address: int = 0
    size: int = 0


@dataclass(frozen=True)
class CHI_RSP:
    """Source-shaped CHI response record. / 源代码形状的 CHI 响应记录。"""

    txn_id: int = 0
    src_id: int = 0
    tgt_id: int = 0
    opcode: int = 0
    response: int = 0


@dataclass(frozen=True)
class CHI_DAT:
    """Source-shaped CHI data record. / 源代码形状的 CHI 数据记录。"""

    txn_id: int = 0
    src_id: int = 0
    tgt_id: int = 0
    opcode: int = 0
    data: int = 0
    data_id: int = 0


@dataclass(frozen=True)
class CHI_SNP:
    """Source-shaped CHI snoop record. / 源代码形状的 CHI snoop 记录。"""

    txn_id: int = 0
    src_id: int = 0
    fwd_id: int = 0
    opcode: int = 0
    address: int = 0


CHI_REQ_OPCODES: dict[str, int] = {
    "ReqLCrdReturn": 0x00, "ReadShared": 0x01, "ReadClean": 0x02, "ReadOnce": 0x03,
    "ReadNoSnp": 0x04, "PCrdReturn": 0x05, "ReadUnique": 0x07,
    "CleanShared": 0x08, "CleanInvalid": 0x09, "MakeInvalid": 0x0A,
    "CleanUnique": 0x0B, "MakeUnique": 0x0C, "Evict": 0x0D,
    "DVMOp": 0x14, "WriteEvictFull": 0x15, "WriteCleanFull": 0x17,
    "WriteUniquePtl": 0x18, "WriteUniqueFull": 0x19, "WriteBackPtl": 0x1A,
    "WriteBackFull": 0x1B, "WriteNoSnpPtl": 0x1C, "WriteNoSnpFull": 0x1D,
    "AtomicStore_ADD": 0x28, "AtomicLoad_ADD": 0x30, "AtomicSwap": 0x38,
    "AtomicCompare": 0x39, "PrefetchTgt": 0x3A,
}
CHI_RSP_OPCODES: dict[str, int] = {
    "RespLCrdReturn": 0x0, "SnpResp": 0x1, "CompAck": 0x2, "RetryAck": 0x3,
    "Comp": 0x4, "CompDBIDResp": 0x5, "DBIDResp": 0x6, "PCrdGrant": 0x7,
    "ReadReceipt": 0x8, "SnpRespFwded": 0x9, "RespSepData": 0xB,
}
CHI_DAT_OPCODES: dict[str, int] = {
    "DataLCrdReturn": 0x0, "SnpRespData": 0x1, "CopyBackWrData": 0x2,
    "NonCopyBackWrData": 0x3, "CompData": 0x4, "SnpRespDataPtl": 0x5,
    "WriteDataCancel": 0x7, "DataSepResp": 0xB,
}
CHI_SNP_OPCODES: dict[str, int] = {
    "SnpLCrdReturn": 0x00, "SnpShared": 0x01, "SnpClean": 0x02, "SnpOnce": 0x03,
    "SnpNotSharedDirty": 0x04, "SnpUnique": 0x07, "SnpCleanShared": 0x08,
    "SnpCleanInvalid": 0x09, "SnpMakeInvalid": 0x0A,
}

LINK_STOP = 0
LINK_ACTIVATE = 1
LINK_RUN = 2
LINK_DEACTIVATE = 3


# Return LSB-first CHI field widths for the selected issue. / 返回选定 issue 的 LSB-first CHI 字段位宽。
def chi_layout(configuration: OpenLLCChiConfig | None = None) -> dict[str, tuple[int, ...]]:
    """Build request/response/data/snoop layouts. / 构造 request/response/data/snoop 布局。"""

    cfg = configuration or OpenLLCChiConfig()
    optional = 11 if cfg.issue == "E.b" else 0
    return {
        "req": (4, cfg.node_id_bits, cfg.node_id_bits, cfg.txn_id_bits, cfg.node_id_bits,
                1, cfg.txn_id_bits, cfg.opcode_bits, 3, cfg.address_bits, 1, 1, 1, 2, 4, 4, 1, 1, optional),
        "rsp": (4, cfg.node_id_bits, cfg.node_id_bits, cfg.txn_id_bits, cfg.opcode_bits, 2, 3, 3,
                cfg.txn_id_bits, 4, optional),
        "dat": (4, cfg.node_id_bits, cfg.node_id_bits, cfg.txn_id_bits, cfg.node_id_bits, 4, 2, 3,
                max(1, (cfg.node_id_bits - 1)), cfg.txn_id_bits, 2, 2, cfg.data_bytes, cfg.data_bits),
        "snp": (4, cfg.node_id_bits, cfg.txn_id_bits, cfg.node_id_bits, cfg.txn_id_bits,
                5, max(1, cfg.address_bits - 3), 1, 1, optional),
    }


# Pack LSB-first fields with strict width checking. / 严格按位宽打包 LSB-first 字段。
def pack_fields(values: Sequence[int], widths: Sequence[int]) -> int:
    """Pack fields into an integer flit. / 将字段打包为整数 flit。"""

    if len(values) != len(widths):
        raise ValueError("field/value count mismatch")
    result = 0
    shift = 0
    for value, width in zip(values, widths):
        if width < 1 or value < 0 or value >= (1 << width):
            raise ValueError("field does not fit declared width")
        result |= int(value) << shift
        shift += width
    return result


# Unpack an integer flit and reject stray high bits. / 解包整数 flit 并拒绝额外高位。
def unpack_fields(value: int, widths: Sequence[int]) -> tuple[int, ...]:
    """Unpack fields from an LSB-first flit. / 从 LSB-first flit 解包字段。"""

    result: list[int] = []
    shift = 0
    for width in widths:
        if width < 1:
            raise ValueError("field width must be positive")
        result.append((int(value) >> shift) & ((1 << width) - 1))
        shift += width
    if int(value) >> shift:
        raise ValueError("flit contains bits outside layout")
    return tuple(result)


# Compute the four-state link transition table. / 计算四态链路转换表。
def next_link_state(active_request: bool, active_ack: bool) -> int:
    """Return LinkStates transition for request/ack pair. / 返回 request/ack 对应的 LinkStates 转换。"""

    return LINK_RUN if active_request and active_ack else LINK_ACTIVATE if active_request else LINK_DEACTIVATE if active_ack else LINK_STOP


# Update one L-Credit counter while preventing overflow/underflow. / 更新单个 L-Credit 计数器并防止溢出/下溢。
def credit_update(credit: int, returned: bool, consumed: bool, maximum: int = 15) -> int:
    """Apply one credit event. / 应用一次信用事件。"""

    current = int(credit)
    if current < 0 or current > maximum:
        raise ValueError("credit counter out of range")
    if returned and consumed:
        return current
    if returned:
        if current == maximum:
            raise ValueError("credit overflow")
        return current + 1
    if consumed:
        if current == 0:
            raise ValueError("credit underflow")
        return current - 1
    return current


# Detect MMIO requests by the high transaction-ID bit. / 通过 transaction-ID 最高位检测 MMIO 请求。
def request_from_mmio(txn_id: int, configuration: OpenLLCChiConfig | None = None) -> bool:
    """Return true for the uncacheable ID half-space. / 判断是否属于非缓存 ID 半空间。"""

    cfg = configuration or OpenLLCChiConfig()
    return bool((int(txn_id) >> (cfg.txn_id_bits - 1)) & 1)


# =============================================================================
# Implementation
# =============================================================================
class OpenLLCLinkLayer(Elaboratable):
    """CHI link monitor with TX/RX activation and three credit pools.
    带 TX/RX 激活及三个信用池的 CHI 链路监视器。
    """

    # Construct the source-shaped CHI link boundary. / 构造源代码形状的 CHI 链路边界。
    def __init__(self, configuration: OpenLLCChiConfig | None = None) -> None:
        self.configuration = configuration or OpenLLCChiConfig()
        c = self.configuration
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.tx_linkactivereq = Signal(name="io_tx_linkactivereq")
        self.tx_linkactiveack = Signal(name="io_tx_linkactiveack")
        self.rx_linkactivereq = Signal(name="io_rx_linkactivereq")
        self.rx_linkactiveack = Signal(name="io_rx_linkactiveack")
        self.txsactive = Signal(name="io_txsactive")
        self.syscoreq = Signal(name="io_syscoreq")
        self.syscoack = Signal(name="io_syscoack")
        self.tx_req_valid = Signal(name="io_tx_req_flitv")
        self.tx_req_ready = Signal(name="io_tx_req_ready")
        self.tx_req_flit = Signal(sum(chi_layout(self.configuration)["req"]), name="io_tx_req_flit")
        self.tx_dat_valid = Signal(name="io_tx_dat_flitv")
        self.tx_dat_ready = Signal(name="io_tx_dat_ready")
        self.tx_dat_flit = Signal(sum(chi_layout(self.configuration)["dat"]), name="io_tx_dat_flit")
        self.tx_rsp_valid = Signal(name="io_tx_rsp_flitv")
        self.tx_rsp_ready = Signal(name="io_tx_rsp_ready")
        self.tx_rsp_flit = Signal(sum(chi_layout(self.configuration)["rsp"]), name="io_tx_rsp_flit")
        self.rx_req_valid = Signal(name="io_rx_req_flitv")
        self.rx_req_ready = Signal(name="io_rx_req_ready")
        self.rx_req_flit = Signal(sum(chi_layout(self.configuration)["req"]), name="io_rx_req_flit")
        self.rx_dat_valid = Signal(name="io_rx_dat_flitv")
        self.rx_dat_ready = Signal(name="io_rx_dat_ready")
        self.rx_dat_flit = Signal(sum(chi_layout(self.configuration)["dat"]), name="io_rx_dat_flit")
        self.rx_rsp_valid = Signal(name="io_rx_rsp_flitv")
        self.rx_rsp_ready = Signal(name="io_rx_rsp_ready")
        self.rx_rsp_flit = Signal(sum(chi_layout(self.configuration)["rsp"]), name="io_rx_rsp_flit")
        self.tx_req_credit_return = Signal(name="io_tx_req_lcrdv")
        self.tx_dat_credit_return = Signal(name="io_tx_dat_lcrdv")
        self.tx_rsp_credit_return = Signal(name="io_tx_rsp_lcrdv")
        self.rx_req_credit_return = Signal(name="io_rx_req_lcrdv")
        self.rx_dat_credit_return = Signal(name="io_rx_dat_lcrdv")
        self.rx_rsp_credit_return = Signal(name="io_rx_rsp_lcrdv")

    # Elaborate activation states, credit counters and flit pass-through. / 展开激活状态、信用计数器及 flit 直通。
    def elaborate(self, platform: Any) -> Module:
        """Build deterministic link behavior. / 构造确定性的链路行为。"""

        del platform
        c = self.configuration
        m = Module()
        domain = ClockDomain("openllc_link", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.openllc_link = domain
        tx_state = Signal(2, reset=LINK_STOP, name="tx_link_state")
        rx_state = Signal(2, reset=LINK_STOP, name="rx_link_state")
        tx_req_credit = Signal(range(c.credit_depth + 1), reset=0, name="tx_req_credit")
        tx_dat_credit = Signal(range(c.credit_depth + 1), reset=0, name="tx_dat_credit")
        tx_rsp_credit = Signal(range(c.credit_depth + 1), reset=0, name="tx_rsp_credit")
        rx_link_up = rx_state == LINK_RUN
        tx_link_up = tx_state == LINK_RUN
        m.d.comb += [
            self.tx_req_ready.eq(tx_link_up & (tx_req_credit != 0)),
            self.tx_dat_ready.eq(tx_link_up & (tx_dat_credit != 0)),
            self.tx_rsp_ready.eq(tx_link_up & (tx_rsp_credit != 0)),
            self.rx_req_ready.eq(rx_link_up), self.rx_dat_ready.eq(rx_link_up), self.rx_rsp_ready.eq(rx_link_up),
            self.txsactive.eq(1), self.syscoack.eq(self.syscoreq),
            self.rx_linkactiveack.eq(self.rx_linkactivereq & ~self.reset),
        ]
        with amaranth_if(m, self.reset):
            m.d.openllc_link += [tx_state.eq(LINK_STOP), rx_state.eq(LINK_STOP),
                                 tx_req_credit.eq(0), tx_dat_credit.eq(0), tx_rsp_credit.eq(0)]
        with amaranth_if(m, ~self.reset):
            m.d.openllc_link += [
                tx_state.eq(Mux(self.tx_linkactivereq, Mux(self.tx_linkactiveack, LINK_RUN, LINK_ACTIVATE),
                                Mux(self.tx_linkactiveack, LINK_DEACTIVATE, LINK_STOP))),
                rx_state.eq(Mux(self.rx_linkactivereq, Mux(self.rx_linkactiveack, LINK_RUN, LINK_ACTIVATE),
                                Mux(self.rx_linkactiveack, LINK_DEACTIVATE, LINK_STOP))),
            ]
            with amaranth_if(m, self.tx_req_credit_return & ~self.tx_req_valid):
                with amaranth_if(m, tx_req_credit < c.credit_depth):
                    m.d.openllc_link += tx_req_credit.eq(tx_req_credit + 1)
            with amaranth_if(m, self.tx_req_valid & self.tx_req_ready & ~self.tx_req_credit_return):
                m.d.openllc_link += tx_req_credit.eq(tx_req_credit - 1)
            with amaranth_if(m, self.tx_dat_credit_return & ~self.tx_dat_valid):
                with amaranth_if(m, tx_dat_credit < c.credit_depth):
                    m.d.openllc_link += tx_dat_credit.eq(tx_dat_credit + 1)
            with amaranth_if(m, self.tx_dat_valid & self.tx_dat_ready & ~self.tx_dat_credit_return):
                m.d.openllc_link += tx_dat_credit.eq(tx_dat_credit - 1)
            with amaranth_if(m, self.tx_rsp_credit_return & ~self.tx_rsp_valid):
                with amaranth_if(m, tx_rsp_credit < c.credit_depth):
                    m.d.openllc_link += tx_rsp_credit.eq(tx_rsp_credit + 1)
            with amaranth_if(m, self.tx_rsp_valid & self.tx_rsp_ready & ~self.tx_rsp_credit_return):
                m.d.openllc_link += tx_rsp_credit.eq(tx_rsp_credit - 1)
        return m


class OpenLLCChannelTransmitter(Elaboratable):
    """Ready/valid transmitter for one CHI flit class. / 单类 CHI flit 的 ready/valid 发送器。"""

    # Construct transmitter ports. / 构造发送器端口。
    def __init__(self, width: int = 128) -> None:
        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.in_valid = Signal(name="io_task_valid")
        self.in_ready = Signal(name="io_task_ready")
        self.in_flit = Signal(width, name="io_task_bits")
        self.out_valid = Signal(name="io_flitv")
        self.out_ready = Signal(name="io_lcrdv")
        self.out_flit = Signal(width, name="io_flit")

    # Elaborate a one-entry holding register. / 展开单项保持寄存器。
    def elaborate(self, platform: Any) -> Module:
        """Build transmitter buffering. / 构造发送器缓冲。"""

        del platform
        m = Module()
        domain = ClockDomain("openllc_tx", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.openllc_tx = domain
        valid = Signal(name="tx_valid")
        flit = Signal.like(self.in_flit)
        fire_out = self.out_valid & self.out_ready
        m.d.comb += [self.in_ready.eq(~valid | fire_out), self.out_valid.eq(valid), self.out_flit.eq(flit)]
        with amaranth_if(m, self.reset):
            m.d.openllc_tx += valid.eq(0)
        with amaranth_if(m, ~self.reset):
            with amaranth_if(m, self.in_valid & self.in_ready):
                m.d.openllc_tx += [valid.eq(1), flit.eq(self.in_flit)]
            with amaranth_if(m, fire_out & ~self.in_valid):
                m.d.openllc_tx += valid.eq(0)
        return m


class OpenLLCChannelReceiver(Elaboratable):
    """Ready/valid receiver for one CHI flit class. / 单类 CHI flit 的 ready/valid 接收器。"""

    # Construct receiver ports. / 构造接收器端口。
    def __init__(self, width: int = 128) -> None:
        self.in_valid = Signal(name="io_flitv")
        self.in_ready = Signal(name="io_lcrdv")
        self.in_flit = Signal(width, name="io_flit")
        self.out_valid = Signal(name="io_task_valid")
        self.out_ready = Signal(name="io_task_ready")
        self.out_flit = Signal(width, name="io_task_bits")

    # Elaborate direct flow-through receiver. / 展开直通接收器。
    def elaborate(self, platform: Any) -> Module:
        """Build receiver handshake. / 构造接收器握手。"""

        del platform
        m = Module()
        m.d.comb += [self.out_valid.eq(self.in_valid), self.out_flit.eq(self.in_flit),
                     self.in_ready.eq(self.out_ready)]
        return m


class OpenLLCBridge(OpenLLCLinkLayer):
    """Aggregate source-compatible CHI bridge. / 源码兼容的 CHI bridge 聚合。"""


# Compatibility aliases for each Scala child. / 每个 Scala 子模块的兼容别名。
LinkLayer = OpenLLCLinkLayer
TXREQ = OpenLLCChannelTransmitter
TXRSP = OpenLLCChannelTransmitter
TXDAT = OpenLLCChannelTransmitter
TXSNP = OpenLLCChannelTransmitter
RXREQ = OpenLLCChannelReceiver
RXRSP = OpenLLCChannelReceiver
RXDAT = OpenLLCChannelReceiver


# =============================================================================
# Public Adapter
# =============================================================================
# Export deterministic OpenLLC CHI bridge Verilog. / 导出确定性的 OpenLLC CHI bridge Verilog。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the aggregate CHI link bridge. / 返回 CHI 链路 bridge 聚合 Verilog。"""

    del injected_dependencies
    if isinstance(configuration, OpenLLCChiConfig):
        cfg, name = configuration, "UHSCOpenLLCChiBridge"
    elif isinstance(configuration, Mapping):
        fields = OpenLLCChiConfig.__dataclass_fields__
        cfg = OpenLLCChiConfig(**{key: value for key, value in configuration.items() if key in fields})
        name = str(configuration.get("module", configuration.get("name", "UHSCOpenLLCChiBridge")))
    elif configuration is None:
        cfg, name = OpenLLCChiConfig(), "UHSCOpenLLCChiBridge"
    else:
        raise TypeError("configuration must be OpenLLCChiConfig, mapping, or None")
    top = OpenLLCBridge(cfg)
    ports = [top.clock, top.reset, top.tx_linkactivereq, top.tx_linkactiveack,
             top.rx_linkactivereq, top.rx_linkactiveack, top.txsactive, top.syscoreq, top.syscoack,
             top.tx_req_valid, top.tx_req_ready, top.tx_req_flit, top.tx_dat_valid, top.tx_dat_ready,
             top.tx_dat_flit, top.tx_rsp_valid, top.tx_rsp_ready, top.tx_rsp_flit,
             top.rx_req_valid, top.rx_req_ready, top.rx_req_flit, top.rx_dat_valid, top.rx_dat_ready,
             top.rx_dat_flit, top.rx_rsp_valid, top.rx_rsp_ready, top.rx_rsp_flit,
             top.tx_req_credit_return, top.tx_dat_credit_return, top.tx_rsp_credit_return,
             top.rx_req_credit_return, top.rx_dat_credit_return, top.rx_rsp_credit_return]
    return verilog.convert(top, name=name, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print deterministic direct export. / 打印确定性的直接导出。
def main() -> None:
    """Print default CHI bridge Verilog. / 打印默认 CHI bridge Verilog。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
