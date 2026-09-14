"""UHSC Kunminghu V2 CoupledL2 TileLink/CHI bridge family.
昆明湖 V2 CoupledL2 TileLink/CHI bridge family 聚合实现。

This aggregate captures the hardware-bearing boundary of the V2 ``tl2chi``
closure.  It keeps CHI message layouts, link states, L-Credit accounting,
transaction-ID banking, MMIO conversion, snoop response handling, and the
single-transaction TL/CHI bridge in one deterministic Amaranth module.  The
locked V2 DefaultConfig selects the TL2TL path, so the CHI path remains a
conditional family until a CHI-enabled top is selected and compared.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# The public boundary preserves the CHI B/C/Eb message constants, the
# ready/valid direction of TL2CHICoupledL2, and the link/credit observations.
# 公共边界保持 CHI B/C/Eb 消息常量、TL2CHICoupledL2 ready/valid 方向以及链路/信用观测点。
__all__ = [
    "CoupledL2BridgeConfig",
    "CHI_CHANNEL_TXREQ",
    "CHI_CHANNEL_TXRSP",
    "CHI_CHANNEL_TXDAT",
    "LINK_STOP",
    "LINK_ACTIVATE",
    "LINK_RUN",
    "LINK_DEACTIVATE",
    "TL_OPCODE_PUTFULL",
    "TL_OPCODE_PUTPARTIAL",
    "TL_OPCODE_ARITHMETIC",
    "TL_OPCODE_LOGICAL",
    "TL_OPCODE_GET",
    "TL_OPCODE_HINT",
    "TL_OPCODE_ACQUIRE_BLOCK",
    "TL_OPCODE_ACQUIRE_PERM",
    "CHI_REQ_OPCODES",
    "CHI_RSP_OPCODES",
    "CHI_SNP_OPCODES",
    "CHI_DAT_OPCODES",
    "CHI_COHERENCE_STATES",
    "CHI_RESP_ERR",
    "CHI_ORDER",
    "issue_widths",
    "chi_layout_widths",
    "pack_fields",
    "unpack_fields",
    "pack_chi_request",
    "unpack_chi_request",
    "pack_chi_response",
    "pack_chi_data",
    "pack_chi_snoop",
    "tl_to_chi_opcode",
    "chi_response_to_tl",
    "credit_step",
    "encode_transaction_id",
    "decode_transaction_id",
    "sam_lookup",
    "snoop_response",
    "CoupledL2Bridge",
    "TL2CHIBridge",
    "TL2CHICoupledL2Bridge",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
CHI_CHANNEL_TXREQ = 0b001
CHI_CHANNEL_TXRSP = 0b010
CHI_CHANNEL_TXDAT = 0b100

LINK_STOP = 0
LINK_ACTIVATE = 1
LINK_RUN = 2
LINK_DEACTIVATE = 3

TL_OPCODE_PUTFULL = 0
TL_OPCODE_PUTPARTIAL = 1
TL_OPCODE_ARITHMETIC = 2
TL_OPCODE_LOGICAL = 3
TL_OPCODE_GET = 4
TL_OPCODE_HINT = 5
TL_OPCODE_ACQUIRE_BLOCK = 6
TL_OPCODE_ACQUIRE_PERM = 7

# V2 CHI Issue B/C/E.b constants copied from tl2chi/chi/Opcode.scala. / 
# 以下常量对应 tl2chi/chi/Opcode.scala 中的 V2 CHI B/C/E.b 编码。
CHI_REQ_OPCODES = {
    "ReqLCrdReturn": 0x00,
    "ReadShared": 0x01,
    "ReadClean": 0x02,
    "ReadOnce": 0x03,
    "ReadNoSnp": 0x04,
    "PCrdReturn": 0x05,
    "ReadUnique": 0x07,
    "CleanShared": 0x08,
    "CleanInvalid": 0x09,
    "MakeInvalid": 0x0A,
    "CleanUnique": 0x0B,
    "MakeUnique": 0x0C,
    "Evict": 0x0D,
    "DVMOp": 0x14,
    "WriteEvictFull": 0x15,
    "WriteCleanFull": 0x17,
    "WriteUniquePtl": 0x18,
    "WriteUniqueFull": 0x19,
    "WriteBackPtl": 0x1A,
    "WriteBackFull": 0x1B,
    "WriteNoSnpPtl": 0x1C,
    "WriteNoSnpFull": 0x1D,
    "WriteUniqueFullStash": 0x20,
    "WriteUniquePtlStash": 0x21,
    "StashOnceShared": 0x22,
    "StashOnceUnique": 0x23,
    "ReadOnceCleanInvalid": 0x24,
    "ReadOnceMakeInvalid": 0x25,
    "ReadNotSharedDirty": 0x26,
    "CleanSharedPersist": 0x27,
    "AtomicStore_ADD": 0x28,
    "AtomicStore_CLR": 0x29,
    "AtomicStore_EOR": 0x2A,
    "AtomicStore_SET": 0x2B,
    "AtomicStore_SMAX": 0x2C,
    "AtomicStore_SMIN": 0x2D,
    "AtomicStore_UMAX": 0x2E,
    "AtomicStore_UMIN": 0x2F,
    "AtomicLoad_ADD": 0x30,
    "AtomicLoad_CLR": 0x31,
    "AtomicLoad_EOR": 0x32,
    "AtomicLoad_SET": 0x33,
    "AtomicLoad_SMAX": 0x34,
    "AtomicLoad_SMIN": 0x35,
    "AtomicLoad_UMAX": 0x36,
    "AtomicLoad_UMIN": 0x37,
    "AtomicSwap": 0x38,
    "AtomicCompare": 0x39,
    "PrefetchTgt": 0x3A,
    "WriteEvictOrEvict": 0x42,
}

CHI_RSP_OPCODES = {
    "RespLCrdReturn": 0x0,
    "SnpResp": 0x1,
    "CompAck": 0x2,
    "RetryAck": 0x3,
    "Comp": 0x4,
    "CompDBIDResp": 0x5,
    "DBIDResp": 0x6,
    "PCrdGrant": 0x7,
    "ReadReceipt": 0x8,
    "SnpRespFwded": 0x9,
    "RespSepData": 0x0B,
    "DBIDRespOrd": 0x0E,
}

CHI_SNP_OPCODES = {
    "SnpLCrdReturn": 0x00,
    "SnpShared": 0x01,
    "SnpClean": 0x02,
    "SnpOnce": 0x03,
    "SnpNotSharedDirty": 0x04,
    "SnpUniqueStash": 0x05,
    "SnpMakeInvalidStash": 0x06,
    "SnpUnique": 0x07,
    "SnpCleanShared": 0x08,
    "SnpCleanInvalid": 0x09,
    "SnpMakeInvalid": 0x0A,
    "SnpStashUnique": 0x0B,
    "SnpStashShared": 0x0C,
    "SnpDVMOp": 0x0D,
    "SnpQuery": 0x10,
    "SnpSharedFwd": 0x11,
    "SnpCleanFwd": 0x12,
    "SnpOnceFwd": 0x13,
    "SnpNotSharedDirtyFwd": 0x14,
    "SnpPreferUnique": 0x15,
    "SnpPreferUniqueFwd": 0x16,
    "SnpUniqueFwd": 0x17,
}

CHI_DAT_OPCODES = {
    "DataLCrdReturn": 0x0,
    "SnpRespData": 0x1,
    "CopyBackWrData": 0x2,
    "NonCopyBackWrData": 0x3,
    "CompData": 0x4,
    "SnpRespDataPtl": 0x5,
    "SnpRespDataFwded": 0x6,
    "WriteDataCancel": 0x7,
    "DataSepResp": 0x0B,
}

CHI_COHERENCE_STATES = {"I": 0b000, "SC": 0b001, "UC": 0b010, "UD": 0b010, "SD": 0b011, "PassDirty": 0b100}
CHI_RESP_ERR = {"OK": 0b00, "EXOK": 0b01, "DERR": 0b10, "NDERR": 0b11}
CHI_ORDER = {"None": 0b00, "RequestAccepted": 0b01, "RequestOrder": 0b10, "OWO": 0b10, "EndpointOrder": 0b11}


@dataclass(frozen=True)
class CoupledL2BridgeConfig:
    """V2 CHI bridge geometry and issue selection. / V2 CHI bridge 几何及 issue 选择。"""

    issue: str = "B"
    address_bits: int = 48
    node_id_bits: int = 7
    transaction_id_bits: int = 8
    lpid_bits: int = 5
    data_bits: int = 256
    qos_bits: int = 4
    size_bits: int = 3
    pcrd_type_bits: int = 4
    mem_attr_bits: int = 4
    order_bits: int = 2
    response_bits: int = 3
    resp_err_bits: int = 2
    fwd_state_bits: int = 3
    credit_num: int = 4
    mmio_entries: int = 4
    banks: int = 1
    bank_bits: int = 0
    source_id: int = 0
    target_id: int = 0
    enable_async: bool = False
    tx_source_ready: bool = False

    # Validate V2 widths and credit geometry. / 校验 V2 位宽与信用几何参数。
    def __post_init__(self) -> None:
        if self.issue not in ("B", "C", "E.b"):
            raise ValueError("issue must be B, C, or E.b")
        integer_fields = (self.address_bits, self.node_id_bits, self.transaction_id_bits, self.lpid_bits,
                          self.data_bits, self.qos_bits, self.size_bits, self.pcrd_type_bits,
                          self.mem_attr_bits, self.order_bits, self.response_bits, self.resp_err_bits,
                          self.fwd_state_bits, self.credit_num, self.mmio_entries)
        if min(integer_fields) < 1 or self.data_bits % 8:
            raise ValueError("all bridge widths must be positive byte-compatible integers")
        if self.address_bits < 44 or self.address_bits > 52:
            raise ValueError("CHI address width must be in [44, 52]")
        if self.credit_num > 15:
            raise ValueError("CHI L-Credit pool is limited to 15")
        if self.banks < 1 or self.bank_bits < 0 or (self.banks > 1 and self.bank_bits < 1):
            raise ValueError("invalid bank geometry")
        if self.banks > 1 and (1 << self.bank_bits) < self.banks:
            raise ValueError("bank_bits cannot encode all banks")


# Return issue-specific opcode field widths from Message.scala. / 返回 Message.scala 的 issue 专用 opcode 位宽。
def issue_widths(issue: str) -> dict[str, int]:
    """Return CHI issue widths. / 返回 CHI issue 位宽。"""

    if issue == "B":
        return {"req_opcode": 6, "rsp_opcode": 4, "snp_opcode": 5, "dat_opcode": 3,
                "node_id": 7, "txn_id": 8, "lpid": 5, "data_source": 3}
    if issue == "C":
        return {"req_opcode": 6, "rsp_opcode": 4, "snp_opcode": 5, "dat_opcode": 4,
                "node_id": 9, "txn_id": 8, "lpid": 5, "data_source": 3}
    if issue == "E.b":
        return {"req_opcode": 7, "rsp_opcode": 5, "snp_opcode": 5, "dat_opcode": 4,
                "node_id": 11, "txn_id": 12, "lpid": 8, "data_source": 4}
    raise ValueError("issue must be B, C, or E.b")


# Return LSB-first field widths for each CHI channel. / 返回各 CHI 通道的 LSB-first 字段位宽。
def chi_layout_widths(configuration: CoupledL2BridgeConfig | None = None) -> dict[str, tuple[int, ...]]:
    """Build deterministic CHI field layouts. / 构造确定性的 CHI 字段布局。"""

    cfg = configuration or CoupledL2BridgeConfig()
    iw = issue_widths(cfg.issue)
    mpam = 11 if cfg.issue == "E.b" else 0
    tag_op = 2 if cfg.issue == "E.b" else 0
    req = (cfg.qos_bits, iw["node_id"], iw["node_id"], iw["txn_id"], iw["node_id"], 1,
           iw["txn_id"], iw["req_opcode"], cfg.size_bits, cfg.address_bits, 1, 1, 1,
           cfg.order_bits, cfg.pcrd_type_bits, cfg.mem_attr_bits, 1, iw["lpid"], 1, 1,
           tag_op, 1, mpam, 4)
    rsp = (cfg.qos_bits, iw["node_id"], iw["node_id"], iw["txn_id"], iw["rsp_opcode"],
           cfg.resp_err_bits, cfg.response_bits, cfg.fwd_state_bits, 3 if cfg.issue == "E.b" else 0,
           iw["txn_id"], cfg.pcrd_type_bits, tag_op, 1)
    dat = (cfg.qos_bits, iw["node_id"], iw["node_id"], iw["txn_id"], iw["node_id"],
           iw["dat_opcode"], cfg.resp_err_bits, cfg.response_bits, iw["data_source"],
           3 if cfg.issue == "E.b" else 0, iw["txn_id"], 2, 2, tag_op,
           cfg.data_bits // 32 if cfg.issue == "E.b" else 0,
           cfg.data_bits // 128 if cfg.issue == "E.b" else 0, 1, 4, cfg.data_bits // 8, cfg.data_bits)
    snp = (cfg.qos_bits, iw["node_id"], iw["txn_id"], iw["node_id"], iw["txn_id"],
           iw["snp_opcode"], cfg.address_bits - 3, 1, 1, 1, 1, mpam)
    return {"req": tuple(x for x in req if x > 0), "rsp": tuple(x for x in rsp if x > 0),
            "dat": tuple(x for x in dat if x > 0), "snp": tuple(x for x in snp if x > 0)}


# =============================================================================
# Implementation
# =============================================================================
# Pack LSB-first fields exactly once, rejecting width/value mismatches. / 按 LSB-first 一次性打包字段并拒绝越界值。
def pack_fields(values: Sequence[int], widths: Sequence[int]) -> int:
    """Pack integer fields from least to most significant. / 从低位到高位打包整数域。"""

    if len(values) != len(widths):
        raise ValueError("field/value count mismatch")
    result = 0
    shift = 0
    for value, width in zip(values, widths):
        if width < 1 or int(value) < 0 or int(value) >= (1 << width):
            raise ValueError("field does not fit declared width")
        result |= int(value) << shift
        shift += width
    return result


# Unpack LSB-first fields and return the consumed width. / 解包 LSB-first 字段并返回消耗的位宽。
def unpack_fields(value: int, widths: Sequence[int]) -> tuple[int, ...]:
    """Unpack integer fields from least to most significant. / 从低位到高位解包整数域。"""

    result: list[int] = []
    shift = 0
    for width in widths:
        if width < 1:
            raise ValueError("field width must be positive")
        result.append((int(value) >> shift) & ((1 << width) - 1))
        shift += width
    if int(value) >> shift:
        raise ValueError("packed value has bits outside declared layout")
    return tuple(result)


# Pack a CHI request using the Bundle.scala declaration order. / 使用 Bundle.scala 声明顺序打包 CHI 请求。
def pack_chi_request(fields: Sequence[int], configuration: CoupledL2BridgeConfig | None = None) -> int:
    """Pack a CHI TXREQ payload. / 打包 CHI TXREQ 载荷。"""

    return pack_fields(fields, chi_layout_widths(configuration)["req"])


# Unpack a CHI request using the frozen V2 layout. / 使用冻结的 V2 布局解包 CHI 请求。
def unpack_chi_request(value: int, configuration: CoupledL2BridgeConfig | None = None) -> tuple[int, ...]:
    """Unpack a CHI TXREQ payload. / 解包 CHI TXREQ 载荷。"""

    return unpack_fields(value, chi_layout_widths(configuration)["req"])


# Pack a CHI response payload. / 打包 CHI TXRSP 载荷。
def pack_chi_response(fields: Sequence[int], configuration: CoupledL2BridgeConfig | None = None) -> int:
    """Pack a CHI TXRSP/RXRSP payload. / 打包 CHI TXRSP/RXRSP 载荷。"""

    return pack_fields(fields, chi_layout_widths(configuration)["rsp"])


# Pack a CHI data payload. / 打包 CHI TXDAT/RXDAT 载荷。
def pack_chi_data(fields: Sequence[int], configuration: CoupledL2BridgeConfig | None = None) -> int:
    """Pack a CHI TXDAT/RXDAT payload. / 打包 CHI TXDAT/RXDAT 载荷。"""

    return pack_fields(fields, chi_layout_widths(configuration)["dat"])


# Pack a CHI snoop payload. / 打包 CHI RXSNP 载荷。
def pack_chi_snoop(fields: Sequence[int], configuration: CoupledL2BridgeConfig | None = None) -> int:
    """Pack a CHI RXSNP payload. / 打包 CHI RXSNP 载荷。"""

    return pack_fields(fields, chi_layout_widths(configuration)["snp"])


# Translate a TileLink opcode to the CHI request opcode used by the bridge. / 将 TileLink 操作码转换为 bridge 使用的 CHI 请求码。
def tl_to_chi_opcode(tl_opcode: int, mmio: bool = False) -> int:
    """Return the V2 CHI request code for one TL operation. / 返回单个 TL 操作对应的 V2 CHI 请求码。"""

    mapping = {
        TL_OPCODE_GET: CHI_REQ_OPCODES["ReadNoSnp"],
        TL_OPCODE_PUTFULL: CHI_REQ_OPCODES["WriteNoSnpPtl" if mmio else "WriteNoSnpFull"],
        TL_OPCODE_PUTPARTIAL: CHI_REQ_OPCODES["WriteNoSnpPtl"],
        TL_OPCODE_ARITHMETIC: CHI_REQ_OPCODES["AtomicLoad_ADD"],
        TL_OPCODE_LOGICAL: CHI_REQ_OPCODES["AtomicLoad_EOR"],
        TL_OPCODE_HINT: CHI_REQ_OPCODES["PrefetchTgt"],
        TL_OPCODE_ACQUIRE_BLOCK: CHI_REQ_OPCODES["ReadShared"],
        TL_OPCODE_ACQUIRE_PERM: CHI_REQ_OPCODES["ReadUnique"],
    }
    if int(tl_opcode) not in mapping:
        raise ValueError("unsupported TileLink opcode")
    return mapping[int(tl_opcode)]


# Convert a CHI response event to a TileLink D-channel response tuple. / 将 CHI 响应事件转换为 TileLink D 通道响应元组。
def chi_response_to_tl(chi_opcode: int, data: int = 0, resp_err: int = 0,
                       source: int = 0, size: int = 0) -> dict[str, int]:
    """Return deterministic TL response fields. / 返回确定性的 TL 响应字段。"""

    read_data = chi_opcode in (CHI_RSP_OPCODES["RespSepData"],) or chi_opcode == CHI_DAT_OPCODES["CompData"]
    if chi_opcode in (CHI_RSP_OPCODES["RetryAck"], CHI_RSP_OPCODES["PCrdGrant"], CHI_RSP_OPCODES["ReadReceipt"]):
        return {"valid": 0, "opcode": 0, "data": 0, "denied": 0, "corrupt": 0,
                "source": int(source), "size": int(size)}
    return {"valid": 1, "opcode": 1 if read_data else 0, "data": int(data),
            "denied": int(resp_err == CHI_RESP_ERR["NDERR"]),
            "corrupt": int(resp_err in (CHI_RESP_ERR["DERR"], CHI_RESP_ERR["NDERR"])),
            "source": int(source), "size": int(size)}


# Advance a CHI L-Credit pool according to Decoupled2LCredit.scala. / 按 Decoupled2LCredit.scala 推进 CHI L-Credit 池。
def credit_step(pool: int, credit_return: bool, consume: bool, state: int = LINK_RUN,
                maximum: int = 15) -> int:
    """Apply one credit return/consume event. / 应用一个信用返还/消耗事件。"""

    current = int(pool)
    if current < 0 or current > maximum:
        raise ValueError("credit pool out of range")
    if int(state) == LINK_STOP:
        credit_return = False
    if credit_return and consume:
        return current
    if credit_return:
        if current == maximum:
            raise ValueError("credit pool overflow")
        return current + 1
    if consume:
        if current == 0:
            raise ValueError("credit pool underflow")
        return current - 1
    return current


# Encode the cacheable/MMIO transaction-ID arrangement in TL2CHICoupledL2.scala. / 编码 TL2CHICoupledL2.scala 的 cacheable/MMIO 事务 ID 排布。
def encode_transaction_id(transaction_id: int, slice_id: int, mmio: bool,
                          banks: int = 1, bank_bits: int = 0, total_bits: int = 8) -> int:
    """Encode a CHI transaction ID with the MMIO marker. / 编码带 MMIO 标志的 CHI 事务 ID。"""

    if total_bits < 2 or transaction_id < 0 or slice_id < 0:
        raise ValueError("invalid transaction ID arguments")
    mask = (1 << total_bits) - 1
    inner = int(transaction_id) & ((1 << (total_bits - 1)) - 1)
    if mmio or banks <= 1:
        return ((1 if mmio else 0) << (total_bits - 1)) | inner
    if bank_bits < 1 or banks > (1 << bank_bits):
        raise ValueError("invalid bank encoding")
    low_bits = total_bits - 1 - bank_bits
    return ((int(slice_id) & ((1 << bank_bits) - 1)) << low_bits) | (inner & ((1 << low_bits) - 1))


# Decode MMIO marker, slice ID, and local transaction ID. / 解码 MMIO 标志、slice ID 及本地事务 ID。
def decode_transaction_id(transaction_id: int, banks: int = 1, bank_bits: int = 0,
                          total_bits: int = 8) -> dict[str, int]:
    """Decode a CHI transaction ID. / 解码 CHI 事务 ID。"""

    value = int(transaction_id) & ((1 << total_bits) - 1)
    mmio = (value >> (total_bits - 1)) & 1
    if mmio or banks <= 1:
        return {"mmio": mmio, "slice_id": 0, "transaction_id": value & ((1 << (total_bits - 1)) - 1)}
    low_bits = total_bits - 1 - bank_bits
    return {"mmio": 0, "slice_id": (value >> low_bits) & ((1 << bank_bits) - 1),
            "transaction_id": value & ((1 << low_bits) - 1)}


# Perform the priority address lookup represented by chi/NetworkLayer.scala. / 执行 chi/NetworkLayer.scala 的优先地址查找。
def sam_lookup(address: int, ranges: Iterable[tuple[int, int, int]]) -> int:
    """Return the first matching target ID from ``(base, mask, target)``. / 返回首个匹配的目标 ID。"""

    value = int(address)
    for base, mask, target in ranges:
        if ((value ^ int(base)) & ~int(mask)) == 0:
            return int(target)
    return 0


# Build a snoop response tuple matching the RXSNP/TXRSP boundary. / 构造匹配 RXSNP/TXRSP 边界的 snoop 响应元组。
def snoop_response(opcode: int, transaction_id: int, source_id: int,
                   dirty: bool = False, forward: bool = False) -> dict[str, int]:
    """Return SnpResp/SnpRespFwded fields. / 返回 SnpResp/SnpRespFwded 字段。"""

    response_opcode = CHI_RSP_OPCODES["SnpRespFwded"] if forward else CHI_RSP_OPCODES["SnpResp"]
    response = CHI_COHERENCE_STATES["UD"] if dirty else CHI_COHERENCE_STATES["UC"]
    return {"opcode": response_opcode, "transaction_id": int(transaction_id), "source_id": int(source_id),
            "resp": response, "fwd_state": CHI_COHERENCE_STATES["UC"] if forward else 0,
            "request_opcode": int(opcode)}


class CoupledL2Bridge(Elaboratable):
    """Single-entry TL/CHI bridge with link and credit control. / 带链路及信用控制的单项 TL/CHI bridge。"""

    # Construct flattened TL, CHI, link, and status ports. / 构造扁平化 TL、CHI、链路及状态端口。
    def __init__(self, configuration: CoupledL2BridgeConfig | None = None,
                 injected_dependencies: Mapping[str, Any] | None = None) -> None:
        del injected_dependencies
        self.configuration = configuration or CoupledL2BridgeConfig()
        c = self.configuration
        iw = issue_widths(c.issue)
        self._ports: list[Signal] = []

        # Add one named public signal and retain it for deterministic export. / 添加命名公共信号并保留以便确定性导出。
        def add(name: str, width: int = 1) -> Signal:
            signal = Signal(max(1, int(width)), name=f"io_{name}")
            setattr(self, name, signal)
            self._ports.append(signal)
            return signal

        self.clock = add("clock")
        self.reset = add("reset")
        self.flush = add("flush")

        # TileLink A/D request and response fields. / TileLink A/D 请求与响应字段。
        for name, width in {
            "tl_req_valid": 1, "tl_req_ready": 1, "tl_req_opcode": 4, "tl_req_param": 3,
            "tl_req_size": c.size_bits, "tl_req_source": iw["txn_id"], "tl_req_address": c.address_bits,
            "tl_req_data": c.data_bits, "tl_req_mask": c.data_bits // 8, "tl_req_mmio": 1,
            "tl_req_slice_id": max(1, c.bank_bits), "tl_req_corrupt": 1,
            "tl_resp_valid": 1, "tl_resp_ready": 1, "tl_resp_opcode": 4, "tl_resp_param": 3,
            "tl_resp_size": c.size_bits, "tl_resp_source": iw["txn_id"], "tl_resp_data": c.data_bits,
            "tl_resp_denied": 1, "tl_resp_corrupt": 1,
        }.items():
            add(name, width)

        # CHI TXREQ channel fields. / CHI TXREQ 通道字段。
        for name, width in {
            "tx_req_valid": 1, "tx_req_ready": 1, "tx_req_qos": c.qos_bits,
            "tx_req_tgt_id": iw["node_id"], "tx_req_src_id": iw["node_id"],
            "tx_req_txn_id": iw["txn_id"], "tx_req_opcode": iw["req_opcode"],
            "tx_req_size": c.size_bits, "tx_req_address": c.address_bits,
            "tx_req_allow_retry": 1, "tx_req_order": c.order_bits,
            "tx_req_pcrd_type": c.pcrd_type_bits, "tx_req_mem_attr": c.mem_attr_bits,
            "tx_req_data": c.data_bits, "tx_req_mask": c.data_bits // 8,
        }.items():
            add(name, width)

        # CHI TXRSP/TXDAT output channels. / CHI TXRSP/TXDAT 输出通道。
        for name, width in {
            "tx_rsp_valid": 1, "tx_rsp_ready": 1, "tx_rsp_opcode": iw["rsp_opcode"],
            "tx_rsp_tgt_id": iw["node_id"], "tx_rsp_src_id": iw["node_id"],
            "tx_rsp_txn_id": iw["txn_id"], "tx_rsp_resp": c.response_bits,
            "tx_rsp_fwd_state": c.fwd_state_bits, "tx_rsp_resp_err": c.resp_err_bits,
            "tx_dat_valid": 1, "tx_dat_ready": 1, "tx_dat_opcode": iw["dat_opcode"],
            "tx_dat_tgt_id": iw["node_id"], "tx_dat_src_id": iw["node_id"],
            "tx_dat_txn_id": iw["txn_id"], "tx_dat_db_id": iw["txn_id"],
            "tx_dat_data_id": 2, "tx_dat_resp": c.response_bits,
            "tx_dat_resp_err": c.resp_err_bits, "tx_dat_be": c.data_bits // 8,
            "tx_dat_data": c.data_bits,
        }.items():
            add(name, width)

        # CHI RXRSP/RXDAT/RXSNP input channels. / CHI RXRSP/RXDAT/RXSNP 输入通道。
        for name, width in {
            "rx_rsp_valid": 1, "rx_rsp_ready": 1, "rx_rsp_opcode": iw["rsp_opcode"],
            "rx_rsp_src_id": iw["node_id"], "rx_rsp_txn_id": iw["txn_id"],
            "rx_rsp_db_id": iw["txn_id"], "rx_rsp_resp": c.response_bits,
            "rx_rsp_resp_err": c.resp_err_bits, "rx_rsp_pcrd_type": c.pcrd_type_bits,
            "rx_dat_valid": 1, "rx_dat_ready": 1, "rx_dat_opcode": iw["dat_opcode"],
            "rx_dat_src_id": iw["node_id"], "rx_dat_txn_id": iw["txn_id"],
            "rx_dat_data_id": 2, "rx_dat_resp": c.response_bits, "rx_dat_resp_err": c.resp_err_bits,
            "rx_dat_data": c.data_bits,
            "rx_snp_valid": 1, "rx_snp_ready": 1, "rx_snp_opcode": iw["snp_opcode"],
            "rx_snp_src_id": iw["node_id"], "rx_snp_txn_id": iw["txn_id"],
            "rx_snp_address": c.address_bits - 3, "rx_snp_fwd_nid": iw["node_id"],
            "rx_snp_fwd_txn_id": iw["txn_id"], "rx_snp_ret_to_src": 1,
        }.items():
            add(name, width)

        # Link monitor and L-Credit observations. / 链路监视器及 L-Credit 观测字段。
        for name, width in {
            "tx_linkactivereq": 1, "tx_linkactiveack": 1, "rx_linkactivereq": 1,
            "rx_linkactiveack": 1, "tx_state": 2, "rx_state": 2, "syscoreq": 1,
            "syscoack": 1, "coherency_enable": 1, "tx_req_credit_return": 1,
            "tx_rsp_credit_return": 1, "tx_dat_credit_return": 1,
            "tx_req_credit_available": 1, "tx_rsp_credit_available": 1,
            "tx_dat_credit_available": 1, "pcrd_query_valid": 1,
            "pcrd_query_type": c.pcrd_type_bits, "pcrd_query_src_id": iw["node_id"],
            "busy": 1, "l2_miss": 1, "flush_done": 1,
        }.items():
            add(name, width)

    # Return all public signals in stable declaration order. / 按稳定声明顺序返回全部公共信号。
    def public_ports(self) -> tuple[Signal, ...]:
        """Return signals used by the deterministic build adapter. / 返回确定性 build adapter 使用的信号。"""

        return tuple(self._ports)

    # Elaborate bridge state, channel conversion, and link credit accounting. / 展开 bridge 状态、通道转换及链路信用计数。
    def elaborate(self, platform: Any) -> Module:
        """Build the synthesizable V2 bridge boundary. / 构造可综合的 V2 bridge 边界。"""

        del platform
        c = self.configuration
        iw = issue_widths(c.issue)
        m = Module()
        domain = ClockDomain("coupled_l2_bridge", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        m.domains.coupled_l2_bridge = domain

        pending = Signal(name="pending")
        req_sent = Signal(name="req_sent")
        write_data_sent = Signal(name="write_data_sent")
        response_pending = Signal(name="response_pending")
        response_opcode = Signal(4, name="response_opcode")
        response_data = Signal(c.data_bits, name="response_data")
        response_source = Signal(iw["txn_id"], name="response_source")
        response_denied = Signal(name="response_denied")
        response_corrupt = Signal(name="response_corrupt")
        req_opcode = Signal(4, name="req_opcode")
        req_size = Signal(c.size_bits, name="req_size")
        req_source = Signal(iw["txn_id"], name="req_source")
        req_address = Signal(c.address_bits, name="req_address")
        req_data = Signal(c.data_bits, name="req_data")
        req_mask = Signal(c.data_bits // 8, name="req_mask")
        req_mmio = Signal(name="req_mmio")
        req_txn = Signal(iw["txn_id"], name="req_txn")
        req_dbid = Signal(iw["txn_id"], name="req_dbid")
        pcrd_wait = Signal(name="pcrd_wait")
        snp_pending = Signal(name="snp_pending")
        snp_opcode = Signal(iw["snp_opcode"], name="snp_opcode")
        snp_txn = Signal(iw["txn_id"], name="snp_txn")
        snp_src = Signal(iw["node_id"], name="snp_src")

        # Credit pools reset full because the asynchronous CHI link starts with
        # the receiver's advertised pool. / 信用池复位为满池，因为异步 CHI 链路以接收端公布的池容量启动。
        credit_reset = c.credit_num if c.tx_source_ready else 0
        tx_req_credit = Signal(range(c.credit_num + 1), reset=credit_reset, name="tx_req_credit")
        tx_rsp_credit = Signal(range(c.credit_num + 1), reset=credit_reset, name="tx_rsp_credit")
        tx_dat_credit = Signal(range(c.credit_num + 1), reset=credit_reset, name="tx_dat_credit")
        tx_state_r = Signal(2, name="tx_state_r")
        rx_state_r = Signal(2, name="rx_state_r")

        # Link state encoding mirrors LinkMonitor.scala's four-state table. / 链路状态编码对应 LinkMonitor.scala 四态表。
        def link_next(active_request: Signal, active_ack: Signal) -> Any:
            """Return combinational next link state. / 返回组合逻辑链路下一状态。"""

            return Mux(active_request, Mux(active_ack, LINK_RUN, LINK_ACTIVATE),
                       Mux(active_ack, LINK_DEACTIVATE, LINK_STOP))

        tx_run = tx_state_r == LINK_RUN
        rx_run = rx_state_r == LINK_RUN
        tx_req_credit_ok = Const(1) if c.tx_source_ready else (tx_req_credit != 0)
        tx_rsp_credit_ok = Const(1) if c.tx_source_ready else (tx_rsp_credit != 0)
        tx_dat_credit_ok = Const(1) if c.tx_source_ready else (tx_dat_credit != 0)
        m.d.comb += [
            self.tx_linkactivereq.eq(~self.flush),
            self.rx_linkactiveack.eq(self.rx_linkactivereq & ~self.flush),
            self.tx_state.eq(tx_state_r), self.rx_state.eq(rx_state_r),
            self.syscoreq.eq(tx_run & rx_run), self.syscoack.eq(tx_run & rx_run),
            self.coherency_enable.eq(tx_run & rx_run),
            self.tl_req_ready.eq(~pending & ~self.flush & (self.tl_req_mmio | (tx_run & rx_run))),
            self.busy.eq(pending | response_pending | snp_pending),
            self.l2_miss.eq(pending & ~req_mmio & (req_opcode == TL_OPCODE_GET)),
            self.flush_done.eq(self.flush & ~pending & ~response_pending & ~snp_pending),
            self.tx_req_valid.eq(pending & ~req_sent & ~pcrd_wait & tx_run & tx_req_credit_ok),
            self.tx_req_qos.eq(0), self.tx_req_tgt_id.eq(c.target_id), self.tx_req_src_id.eq(c.source_id),
            self.tx_req_txn_id.eq(req_txn), self.tx_req_size.eq(req_size),
            self.tx_req_address.eq(req_address), self.tx_req_allow_retry.eq(1),
            self.tx_req_order.eq(CHI_ORDER["EndpointOrder"] if c.issue != "B" else CHI_ORDER["RequestOrder"]),
            self.tx_req_pcrd_type.eq(0), self.tx_req_mem_attr.eq(0), self.tx_req_data.eq(req_data),
            self.tx_req_mask.eq(req_mask),
            self.tx_dat_valid.eq(write_data_sent & ~self.flush & tx_run & tx_dat_credit_ok),
            self.tx_dat_tgt_id.eq(c.target_id), self.tx_dat_src_id.eq(c.source_id),
            self.tx_dat_txn_id.eq(req_txn), self.tx_dat_db_id.eq(req_dbid),
            self.tx_dat_data_id.eq(0), self.tx_dat_resp.eq(CHI_COHERENCE_STATES["I"]),
            self.tx_dat_resp_err.eq(CHI_RESP_ERR["OK"]), self.tx_dat_be.eq(req_mask), self.tx_dat_data.eq(req_data),
            self.tx_dat_opcode.eq(CHI_DAT_OPCODES["NonCopyBackWrData"]),
            self.tx_rsp_valid.eq(snp_pending & ~self.flush & rx_run & tx_rsp_credit_ok),
            self.tx_rsp_tgt_id.eq(snp_src), self.tx_rsp_src_id.eq(c.source_id), self.tx_rsp_txn_id.eq(snp_txn),
            self.tx_rsp_opcode.eq(Mux(
                (self.rx_snp_opcode == CHI_SNP_OPCODES["SnpSharedFwd"]) |
                (self.rx_snp_opcode == CHI_SNP_OPCODES["SnpCleanFwd"]) |
                (self.rx_snp_opcode == CHI_SNP_OPCODES["SnpOnceFwd"]) |
                (self.rx_snp_opcode == CHI_SNP_OPCODES["SnpUniqueFwd"]),
                CHI_RSP_OPCODES["SnpRespFwded"], CHI_RSP_OPCODES["SnpResp"])),
            self.tx_rsp_resp.eq(CHI_COHERENCE_STATES["UC"]), self.tx_rsp_fwd_state.eq(CHI_COHERENCE_STATES["UC"]),
            self.tx_rsp_resp_err.eq(CHI_RESP_ERR["OK"]),
            self.rx_rsp_ready.eq(pending & ~self.flush), self.rx_dat_ready.eq(pending & ~self.flush & ~response_pending),
            self.rx_snp_ready.eq(~snp_pending & ~self.flush & rx_run),
            self.tl_resp_valid.eq(response_pending & ~self.flush), self.tl_resp_opcode.eq(response_opcode),
            self.tl_resp_param.eq(0), self.tl_resp_size.eq(req_size), self.tl_resp_source.eq(response_source),
            self.tl_resp_data.eq(response_data), self.tl_resp_denied.eq(response_denied), self.tl_resp_corrupt.eq(response_corrupt),
            self.pcrd_query_valid.eq(pcrd_wait), self.pcrd_query_type.eq(self.rx_rsp_pcrd_type),
            self.pcrd_query_src_id.eq(self.rx_rsp_src_id),
            self.tx_req_credit_available.eq(tx_req_credit_ok), self.tx_rsp_credit_available.eq(tx_rsp_credit_ok),
            self.tx_dat_credit_available.eq(tx_dat_credit_ok),
        ]

        # Derive the request opcode in a combinational expression to keep the
        # output stable while ready is low. / 组合推导请求操作码，使 ready 为低时输出保持稳定。
        m.d.comb += self.tx_req_opcode.eq(Mux(req_mmio & (req_opcode == TL_OPCODE_PUTFULL),
                                               CHI_REQ_OPCODES["WriteNoSnpPtl"],
                                               Mux(req_opcode == TL_OPCODE_GET, CHI_REQ_OPCODES["ReadNoSnp"],
                                                   Mux(req_opcode == TL_OPCODE_PUTPARTIAL, CHI_REQ_OPCODES["WriteNoSnpPtl"],
                                                       Mux(req_opcode == TL_OPCODE_PUTFULL, CHI_REQ_OPCODES["WriteNoSnpFull"],
                                                           CHI_REQ_OPCODES["ReadShared"])))))

        with m.If(self.reset | self.flush):
            m.d.coupled_l2_bridge += [pending.eq(0), req_sent.eq(0), write_data_sent.eq(0), response_pending.eq(0),
                                       response_opcode.eq(0), response_data.eq(0), response_source.eq(0),
                                       response_denied.eq(0), response_corrupt.eq(0), pcrd_wait.eq(0), snp_pending.eq(0),
                                       tx_req_credit.eq(credit_reset), tx_rsp_credit.eq(credit_reset),
                                       tx_dat_credit.eq(credit_reset), tx_state_r.eq(LINK_STOP), rx_state_r.eq(LINK_STOP)]
        with m.Else():
            m.d.coupled_l2_bridge += [tx_state_r.eq(link_next(self.tx_linkactivereq, self.tx_linkactiveack)),
                                       rx_state_r.eq(link_next(self.rx_linkactivereq, self.rx_linkactiveack))]

            # Return credits and consume one credit per accepted flit. / 每次 flit 握手返还或消耗一个信用。
            if not c.tx_source_ready:
                with m.If(self.tx_req_credit_return & ~self.tx_req_valid):
                    with m.If(tx_req_credit < c.credit_num):
                        m.d.coupled_l2_bridge += tx_req_credit.eq(tx_req_credit + 1)
                with m.Elif(self.tx_req_valid & self.tx_req_ready):
                    with m.If(tx_req_credit != 0):
                        m.d.coupled_l2_bridge += tx_req_credit.eq(tx_req_credit - 1)
                with m.If(self.tx_rsp_credit_return & ~self.tx_rsp_valid):
                    with m.If(tx_rsp_credit < c.credit_num):
                        m.d.coupled_l2_bridge += tx_rsp_credit.eq(tx_rsp_credit + 1)
                with m.Elif(self.tx_rsp_valid & self.tx_rsp_ready):
                    with m.If(tx_rsp_credit != 0):
                        m.d.coupled_l2_bridge += tx_rsp_credit.eq(tx_rsp_credit - 1)
                with m.If(self.tx_dat_credit_return & ~self.tx_dat_valid):
                    with m.If(tx_dat_credit < c.credit_num):
                        m.d.coupled_l2_bridge += tx_dat_credit.eq(tx_dat_credit + 1)
                with m.Elif(self.tx_dat_valid & self.tx_dat_ready):
                    with m.If(tx_dat_credit != 0):
                        m.d.coupled_l2_bridge += tx_dat_credit.eq(tx_dat_credit - 1)

            with m.If(self.tl_req_valid & self.tl_req_ready):
                m.d.coupled_l2_bridge += [pending.eq(1), req_sent.eq(0), write_data_sent.eq(0), response_pending.eq(0),
                                           req_opcode.eq(self.tl_req_opcode), req_size.eq(self.tl_req_size),
                                           req_source.eq(self.tl_req_source), response_source.eq(self.tl_req_source),
                                           req_address.eq(self.tl_req_address), req_data.eq(self.tl_req_data),
                                           req_mask.eq(self.tl_req_mask), req_mmio.eq(self.tl_req_mmio),
                                           req_txn.eq(self.tl_req_source), req_dbid.eq(0), pcrd_wait.eq(0)]

            with m.If(self.tx_req_valid & self.tx_req_ready):
                m.d.coupled_l2_bridge += req_sent.eq(1)

            with m.If(self.rx_rsp_valid & self.rx_rsp_ready):
                with m.If(self.rx_rsp_opcode == CHI_RSP_OPCODES["RetryAck"]):
                    m.d.coupled_l2_bridge += [req_sent.eq(0), pcrd_wait.eq(1)]
                with m.Elif(self.rx_rsp_opcode == CHI_RSP_OPCODES["PCrdGrant"]):
                    m.d.coupled_l2_bridge += pcrd_wait.eq(0)
                with m.Elif((self.rx_rsp_opcode == CHI_RSP_OPCODES["DBIDResp"]) |
                            (self.rx_rsp_opcode == CHI_RSP_OPCODES["CompDBIDResp"])):
                    m.d.coupled_l2_bridge += req_dbid.eq(self.rx_rsp_db_id)
                    with m.If((req_opcode == TL_OPCODE_PUTFULL) | (req_opcode == TL_OPCODE_PUTPARTIAL)):
                        m.d.coupled_l2_bridge += write_data_sent.eq(1)
                    with m.If(self.rx_rsp_opcode == CHI_RSP_OPCODES["CompDBIDResp"]):
                        m.d.coupled_l2_bridge += [response_pending.eq(1), response_opcode.eq(0),
                                                   response_denied.eq(self.rx_rsp_resp_err == CHI_RESP_ERR["NDERR"]),
                                                   response_corrupt.eq(self.rx_rsp_resp_err != CHI_RESP_ERR["OK"])]
                with m.Elif((self.rx_rsp_opcode == CHI_RSP_OPCODES["Comp"]) |
                            (self.rx_rsp_opcode == CHI_RSP_OPCODES["CompAck"])):
                    m.d.coupled_l2_bridge += [response_pending.eq(1), response_opcode.eq(0),
                                               response_denied.eq(self.rx_rsp_resp_err == CHI_RESP_ERR["NDERR"]),
                                               response_corrupt.eq(self.rx_rsp_resp_err != CHI_RESP_ERR["OK"])]

            with m.If(self.rx_dat_valid & self.rx_dat_ready):
                m.d.coupled_l2_bridge += [response_pending.eq(1), response_opcode.eq(1), response_data.eq(self.rx_dat_data),
                                           response_denied.eq(self.rx_dat_resp_err == CHI_RESP_ERR["NDERR"]),
                                           response_corrupt.eq(self.rx_dat_resp_err != CHI_RESP_ERR["OK"])]

            with m.If(self.tx_dat_valid & self.tx_dat_ready):
                m.d.coupled_l2_bridge += write_data_sent.eq(0)

            with m.If(self.tl_resp_valid & self.tl_resp_ready):
                m.d.coupled_l2_bridge += [response_pending.eq(0), pending.eq(0), req_sent.eq(0), write_data_sent.eq(0)]

            with m.If(self.rx_snp_valid & self.rx_snp_ready):
                m.d.coupled_l2_bridge += [snp_pending.eq(1), snp_opcode.eq(self.rx_snp_opcode),
                                           snp_txn.eq(self.rx_snp_txn_id), snp_src.eq(self.rx_snp_src_id)]
            with m.If(self.tx_rsp_valid & self.tx_rsp_ready):
                m.d.coupled_l2_bridge += snp_pending.eq(0)

        return m


# Compatibility names retain the Scala family concepts without changing the
# project-facing UHSC generated module name. / 兼容名称保留 Scala family 概念，同时不改变 UHSC 生成模块名。
TL2CHIBridge = CoupledL2Bridge
TL2CHICoupledL2Bridge = CoupledL2Bridge


# =============================================================================
# Public Adapter
# =============================================================================
# Export deterministic bridge Verilog with an explicit dependency injection slot. / 导出带显式依赖注入槽的确定性 bridge Verilog。
def build_verilog(configuration, injected_dependencies):
    """Return Verilog for the aggregate CoupledL2 CHI bridge. / 返回聚合 CoupledL2 CHI bridge 的 Verilog。"""

    del injected_dependencies
    if isinstance(configuration, CoupledL2BridgeConfig):
        cfg = configuration
        name = "UHSCCoupledL2Bridge"
    elif isinstance(configuration, dict):
        fields = CoupledL2BridgeConfig.__dataclass_fields__
        values = {key: value for key, value in configuration.items() if key in fields}
        cfg = CoupledL2BridgeConfig(**values)
        name = str(configuration.get("module", configuration.get("name", "UHSCCoupledL2Bridge")))
    elif configuration is None:
        cfg = CoupledL2BridgeConfig()
        name = "UHSCCoupledL2Bridge"
    else:
        raise TypeError("configuration must be CoupledL2BridgeConfig, dict, or None")
    top = CoupledL2Bridge(cfg)
    return verilog.convert(top, name=name, ports=list(top.public_ports()), emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
# Print a deterministic default export when invoked directly. / 直接调用时打印确定性的默认导出。
def main() -> None:
    """Print default bridge Verilog. / 打印默认 bridge Verilog。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
