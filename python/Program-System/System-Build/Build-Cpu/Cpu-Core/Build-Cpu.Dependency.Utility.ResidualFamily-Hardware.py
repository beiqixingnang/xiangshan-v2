"""Implement source-backed V2 utility leaves behind one aggregate adapter.
以单一聚合适配器实现有来源依据的 V2 工具叶模块。
"""
from __future__ import annotations

from typing import Any

from amaranth import Array, Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


COVERED_MODULES = ('CSA3to2', 'CSA3to2_20', 'CSA3to2_24', 'CSA4to2', 'CSA_Nto2With3to2MainPipeline', 'ClockGate', 'DebugTransportModuleJTAG', 'IDPool', 'JtagStateMachine', 'JtagTapController', 'MaxPeriodFibonacciLFSR', 'MaxPeriodFibonacciLFSR_3', 'OverrideableQueue', 'OverrideableQueue_1', 'TimeAsync', 'r4_qds_v2', 'r4_qds_v2_spec', 'skidBufferConnect', 'PrintCommitIDModule')
IMPLEMENTED_MEMBERS = (
    'CSA3to2',
    'CSA3to2_20',
    'CSA3to2_24',
    'CSA4to2',
    'IDPool',
    'JtagStateMachine',
    'MaxPeriodFibonacciLFSR',
    'MaxPeriodFibonacciLFSR_3',
    'OverrideableQueue',
    'OverrideableQueue_1',
    'TimeAsync',
    'r4_qds_v2',
    'r4_qds_v2_spec',
)
CONTRACT_ONLY_MEMBERS = tuple(name for name in COVERED_MODULES if name not in IMPLEMENTED_MEMBERS)

__all__ = [
    "COVERED_MODULES",
    "IMPLEMENTED_MEMBERS",
    "CONTRACT_ONLY_MEMBERS",
    "PORT_SPECS",
    "UtilityResidualFamily",
    "build_verilog",
    "main",
]

PortSpec = tuple[str, str, int]


# =============================================================================
# Module Contract
# =============================================================================
PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    'CSA3to2': (
        ('io_in_a', 'input', 107),
        ('io_in_b', 'input', 107),
        ('io_in_c', 'input', 107),
        ('io_out_sum', 'output', 107),
        ('io_out_car', 'output', 107),
    ),
    'CSA3to2_20': (
        ('io_in_a', 'input', 200),
        ('io_in_b', 'input', 200),
        ('io_in_c', 'input', 200),
        ('io_out_sum', 'output', 200),
        ('io_out_car', 'output', 200),
    ),
    'CSA3to2_24': (
        ('io_in_a', 'input', 72),
        ('io_in_b', 'input', 72),
        ('io_in_c', 'input', 72),
        ('io_out_sum', 'output', 72),
        ('io_out_car', 'output', 72),
    ),
    'CSA4to2': (
        ('io_in_a', 'input', 107),
        ('io_in_b', 'input', 107),
        ('io_in_c', 'input', 107),
        ('io_in_d', 'input', 107),
        ('io_out_sum', 'output', 107),
        ('io_out_car', 'output', 107),
    ),
    'CSA_Nto2With3to2MainPipeline': (
        ('clock', 'input', 1),
        ('io_fire', 'input', 1),
        ('io_in_0', 'input', 107),
        ('io_in_1', 'input', 107),
        ('io_in_2', 'input', 107),
        ('io_in_3', 'input', 107),
        ('io_in_4', 'input', 107),
        ('io_in_5', 'input', 107),
        ('io_in_6', 'input', 107),
        ('io_in_7', 'input', 107),
        ('io_in_8', 'input', 107),
        ('io_in_9', 'input', 107),
        ('io_in_10', 'input', 107),
        ('io_in_11', 'input', 107),
        ('io_in_12', 'input', 107),
        ('io_in_13', 'input', 107),
        ('io_in_14', 'input', 107),
        ('io_in_15', 'input', 107),
        ('io_in_16', 'input', 107),
        ('io_in_17', 'input', 107),
        ('io_in_18', 'input', 107),
        ('io_in_19', 'input', 107),
        ('io_in_20', 'input', 107),
        ('io_in_21', 'input', 107),
        ('io_in_22', 'input', 107),
        ('io_in_23', 'input', 107),
        ('io_in_24', 'input', 107),
        ('io_in_25', 'input', 107),
        ('io_in_26', 'input', 107),
        ('io_out_sum', 'output', 107),
        ('io_out_car', 'output', 107),
    ),
    'ClockGate': (
    ),
    'DebugTransportModuleJTAG': (
        ('io_jtag_clock', 'input', 1),
        ('io_jtag_reset', 'input', 1),
        ('io_dmi_req_ready', 'input', 1),
        ('io_dmi_req_valid', 'output', 1),
        ('io_dmi_req_bits_addr', 'output', 7),
        ('io_dmi_req_bits_data', 'output', 32),
        ('io_dmi_req_bits_op', 'output', 2),
        ('io_dmi_resp_ready', 'output', 1),
        ('io_dmi_resp_valid', 'input', 1),
        ('io_dmi_resp_bits_data', 'input', 32),
        ('io_dmi_resp_bits_resp', 'input', 2),
        ('io_jtag_TMS', 'input', 1),
        ('io_jtag_TDI', 'input', 1),
        ('io_jtag_TDO_data', 'output', 1),
        ('io_jtag_TDO_driven', 'output', 1),
        ('io_jtag_mfr_id', 'input', 11),
        ('io_jtag_part_number', 'input', 16),
        ('io_jtag_version', 'input', 4),
    ),
    'IDPool': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_free_valid', 'input', 1),
        ('io_free_bits', 'input', 3),
        ('io_alloc_ready', 'input', 1),
        ('io_alloc_valid', 'output', 1),
        ('io_alloc_bits', 'output', 3),
    ),
    'JtagStateMachine': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_tms', 'input', 1),
        ('io_currState', 'output', 4),
    ),
    'JtagTapController': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_jtag_TMS', 'input', 1),
        ('io_jtag_TDI', 'input', 1),
        ('io_jtag_TDO_data', 'output', 1),
        ('io_jtag_TDO_driven', 'output', 1),
        ('io_control_jtag_reset', 'input', 1),
        ('io_output_instruction', 'output', 5),
        ('io_output_tapIsInTestLogicReset', 'output', 1),
        ('io_dataChainOut_shift', 'output', 1),
        ('io_dataChainOut_data', 'output', 1),
        ('io_dataChainOut_capture', 'output', 1),
        ('io_dataChainOut_update', 'output', 1),
        ('io_dataChainIn_data', 'input', 1),
    ),
    'MaxPeriodFibonacciLFSR': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_out_0', 'output', 1),
        ('io_out_1', 'output', 1),
        ('io_out_2', 'output', 1),
        ('io_out_3', 'output', 1),
        ('io_out_4', 'output', 1),
        ('io_out_5', 'output', 1),
        ('io_out_6', 'output', 1),
        ('io_out_7', 'output', 1),
        ('io_out_8', 'output', 1),
        ('io_out_9', 'output', 1),
        ('io_out_10', 'output', 1),
        ('io_out_11', 'output', 1),
        ('io_out_12', 'output', 1),
        ('io_out_13', 'output', 1),
        ('io_out_14', 'output', 1),
    ),
    'MaxPeriodFibonacciLFSR_3': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_increment', 'input', 1),
        ('io_out_0', 'output', 1),
        ('io_out_1', 'output', 1),
        ('io_out_2', 'output', 1),
        ('io_out_3', 'output', 1),
        ('io_out_4', 'output', 1),
        ('io_out_5', 'output', 1),
        ('io_out_6', 'output', 1),
        ('io_out_7', 'output', 1),
        ('io_out_8', 'output', 1),
        ('io_out_9', 'output', 1),
        ('io_out_10', 'output', 1),
        ('io_out_11', 'output', 1),
        ('io_out_12', 'output', 1),
        ('io_out_13', 'output', 1),
        ('io_out_14', 'output', 1),
        ('io_out_15', 'output', 1),
    ),
    'OverrideableQueue': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_in_valid', 'input', 1),
        ('io_in_bits_pht_index', 'input', 5),
        ('io_in_bits_pht_tag', 'input', 13),
        ('io_in_bits_region_paddr', 'input', 40),
        ('io_in_bits_region_vaddr', 'input', 40),
        ('io_in_bits_region_offset', 'input', 4),
        ('io_out_ready', 'input', 1),
        ('io_out_valid', 'output', 1),
        ('io_out_bits_pht_index', 'output', 5),
        ('io_out_bits_pht_tag', 'output', 13),
        ('io_out_bits_region_paddr', 'output', 40),
        ('io_out_bits_region_vaddr', 'output', 40),
        ('io_out_bits_region_offset', 'output', 4),
    ),
    'OverrideableQueue_1': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_in_valid', 'input', 1),
        ('io_in_bits_pht_index', 'input', 5),
        ('io_in_bits_pht_tag', 'input', 13),
        ('io_in_bits_region_bits', 'input', 16),
        ('io_in_bits_region_bit_single', 'input', 16),
        ('io_in_bits_region_offset', 'input', 4),
        ('io_in_bits_access_cnt', 'input', 4),
        ('io_in_bits_decr_mode', 'input', 1),
        ('io_in_bits_single_update', 'input', 1),
        ('io_in_bits_has_been_signal_updated', 'input', 1),
        ('io_out_ready', 'input', 1),
        ('io_out_valid', 'output', 1),
        ('io_out_bits_pht_index', 'output', 5),
        ('io_out_bits_pht_tag', 'output', 13),
        ('io_out_bits_region_bits', 'output', 16),
        ('io_out_bits_region_bit_single', 'output', 16),
        ('io_out_bits_region_offset', 'output', 4),
        ('io_out_bits_access_cnt', 'output', 4),
        ('io_out_bits_decr_mode', 'output', 1),
        ('io_out_bits_single_update', 'output', 1),
        ('io_out_bits_has_been_signal_updated', 'output', 1),
    ),
    'TimeAsync': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_i_time_valid', 'input', 1),
        ('io_i_time_bits', 'input', 64),
        ('io_o_time_bits', 'output', 64),
    ),
    'r4_qds_v2': (
        ('io_rem_i', 'input', 6),
        ('io_quo_dig_o', 'output', 5),
    ),
    'r4_qds_v2_spec': (
        ('io_rem_i', 'input', 7),
        ('io_divisor_mul_pos_2_i', 'input', 7),
        ('io_divisor_mul_pos_1_i', 'input', 7),
        ('io_divisor_mul_neg_1_i', 'input', 7),
        ('io_divisor_mul_neg_2_i', 'input', 7),
        ('io_prev_quo_dig_i', 'input', 5),
        ('io_quo_dig_o', 'output', 5),
    ),
    'skidBufferConnect': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_in_ready', 'output', 1),
        ('io_in_valid', 'input', 1),
        ('io_in_bits_flowMask', 'input', 16),
        ('io_in_bits_data', 'input', 128),
        ('io_in_bits_baseAddr', 'input', 64),
        ('io_in_bits_uopAddr', 'input', 64),
        ('io_in_bits_stride', 'input', 128),
        ('io_in_bits_flowNum', 'input', 5),
        ('io_in_bits_eew', 'input', 2),
        ('io_in_bits_sew', 'input', 3),
        ('io_in_bits_emul', 'input', 3),
        ('io_in_bits_lmul', 'input', 3),
        ('io_in_bits_instType', 'input', 3),
        ('io_in_bits_indexedSplitOffset', 'input', 5),
        ('io_in_bits_uop_ftqPtr_flag', 'input', 1),
        ('io_in_bits_uop_ftqPtr_value', 'input', 6),
        ('io_in_bits_uop_ftqOffset', 'input', 4),
        ('io_in_bits_uop_fuOpType', 'input', 9),
        ('io_in_bits_uop_vpu_vstart', 'input', 8),
        ('io_in_bits_uop_vpu_vuopIdx', 'input', 7),
        ('io_in_bits_uop_vpu_veew', 'input', 2),
        ('io_in_bits_uop_uopIdx', 'input', 7),
        ('io_in_bits_uop_pdest', 'input', 8),
        ('io_in_bits_uop_robIdx_flag', 'input', 1),
        ('io_in_bits_uop_robIdx_value', 'input', 8),
        ('io_in_bits_uop_lqIdx_flag', 'input', 1),
        ('io_in_bits_uop_lqIdx_value', 'input', 7),
        ('io_in_bits_uop_sqIdx_flag', 'input', 1),
        ('io_in_bits_uop_sqIdx_value', 'input', 6),
        ('io_in_bits_preIsSplit', 'input', 1),
        ('io_in_bits_mBIndex', 'input', 4),
        ('io_in_bits_alignedType', 'input', 3),
        ('io_in_bits_indexVlMaxInVd', 'input', 8),
        ('io_in_bits_usLowBitsAddr', 'input', 4),
        ('io_in_bits_usAligned128', 'input', 1),
        ('io_in_bits_usMask', 'input', 32),
        ('io_in_bits_isVecPartReplay', 'input', 1),
        ('io_in_bits_vecReplayFlowMask', 'input', 16),
        ('io_flush', 'input', 1),
        ('io_out_ready', 'input', 1),
        ('io_out_valid', 'output', 1),
        ('io_out_bits_flowMask', 'output', 16),
        ('io_out_bits_data', 'output', 128),
        ('io_out_bits_baseAddr', 'output', 64),
        ('io_out_bits_uopAddr', 'output', 64),
        ('io_out_bits_stride', 'output', 128),
        ('io_out_bits_flowNum', 'output', 5),
        ('io_out_bits_eew', 'output', 2),
        ('io_out_bits_sew', 'output', 3),
        ('io_out_bits_emul', 'output', 3),
        ('io_out_bits_lmul', 'output', 3),
        ('io_out_bits_instType', 'output', 3),
        ('io_out_bits_indexedSplitOffset', 'output', 5),
        ('io_out_bits_uop_exceptionVec_5', 'output', 1),
        ('io_out_bits_uop_exceptionVec_13', 'output', 1),
        ('io_out_bits_uop_exceptionVec_19', 'output', 1),
        ('io_out_bits_uop_exceptionVec_21', 'output', 1),
        ('io_out_bits_uop_trigger', 'output', 4),
        ('io_out_bits_uop_preDecodeInfo_isRVC', 'output', 1),
        ('io_out_bits_uop_ftqPtr_flag', 'output', 1),
        ('io_out_bits_uop_ftqPtr_value', 'output', 6),
        ('io_out_bits_uop_ftqOffset', 'output', 4),
        ('io_out_bits_uop_fuOpType', 'output', 9),
        ('io_out_bits_uop_rfWen', 'output', 1),
        ('io_out_bits_uop_fpWen', 'output', 1),
        ('io_out_bits_uop_vpu_vstart', 'output', 8),
        ('io_out_bits_uop_vpu_vuopIdx', 'output', 7),
        ('io_out_bits_uop_vpu_veew', 'output', 2),
        ('io_out_bits_uop_uopIdx', 'output', 7),
        ('io_out_bits_uop_pdest', 'output', 8),
        ('io_out_bits_uop_robIdx_flag', 'output', 1),
        ('io_out_bits_uop_robIdx_value', 'output', 8),
        ('io_out_bits_uop_storeSetHit', 'output', 1),
        ('io_out_bits_uop_waitForRobIdx_flag', 'output', 1),
        ('io_out_bits_uop_waitForRobIdx_value', 'output', 8),
        ('io_out_bits_uop_loadWaitBit', 'output', 1),
        ('io_out_bits_uop_loadWaitStrict', 'output', 1),
        ('io_out_bits_uop_lqIdx_flag', 'output', 1),
        ('io_out_bits_uop_lqIdx_value', 'output', 7),
        ('io_out_bits_uop_sqIdx_flag', 'output', 1),
        ('io_out_bits_uop_sqIdx_value', 'output', 6),
        ('io_out_bits_preIsSplit', 'output', 1),
        ('io_out_bits_mBIndex', 'output', 4),
        ('io_out_bits_alignedType', 'output', 3),
        ('io_out_bits_indexVlMaxInVd', 'output', 8),
        ('io_out_bits_usLowBitsAddr', 'output', 4),
        ('io_out_bits_usAligned128', 'output', 1),
        ('io_out_bits_usMask', 'output', 32),
        ('io_out_bits_isVecPartReplay', 'output', 1),
        ('io_out_bits_vecReplayFlowMask', 'output', 16),
    ),
    'PrintCommitIDModule': (
        ('hartID', 'input', 6),
        ('commitID', 'input', 40),
        ('dirty', 'input', 1),
    ),
}


# =============================================================================
# Configuration
# =============================================================================
_STATEFUL_MEMBERS = {
    "IDPool",
    "JtagStateMachine",
    "MaxPeriodFibonacciLFSR",
    "MaxPeriodFibonacciLFSR_3",
    "OverrideableQueue",
    "OverrideableQueue_1",
    "TimeAsync",
}


# Return the lowest asserted bit index. / 返回最低有效位索引。
def _priority_index(bits: Any, width: int) -> Any:
    result: Any = Const(0, max(1, (width - 1).bit_length()))
    for index in reversed(range(width)):
        result = Mux(bits[index], index, result)
    return result


# Return one four-bit radix-4 sign window. / 返回一个四位 radix-4 符号窗口。
def _qds_sign_window(base: Any) -> Any:
    return Cat((base + 0x1A)[6], (base + 0x08)[6], (base - 0x06)[6], (base - 0x18)[6])


# Encode a four-bit sign window as one-hot quotient digits. / 将四位符号窗口编码为商数字 one-hot。
def _qds_digit(signs: Any) -> Any:
    return Cat(
        signs[2:4] == 0,
        signs[2:4] == 2,
        signs[1:3] == 2,
        signs[0:2] == 2,
        signs[0:2].all(),
    )


# =============================================================================
# Implementation
# =============================================================================
class UtilityResidualFamily(Elaboratable):
    """One exact V2 utility member. / 一个精确的 V2 工具成员。"""

    # Declare one selected member's exact public ports. / 声明选定成员的精确公共端口。
    def __init__(self, member: str = COVERED_MODULES[0]) -> None:
        if member not in PORT_SPECS:
            raise ValueError(member)
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports = {name: Signal(width, name=name) for name, _direction, width in self.specs}

    # Add the locked asynchronous-reset clock domain. / 添加锁定的异步复位时钟域。
    def _add_sync_domain(self, module: Module) -> None:
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.ports["clock"]
        domain.rst = self.ports["reset"]
        module.domains += domain

    # Implement a three-input carry-save compressor. / 实现三输入保留进位压缩器。
    def _csa3(self, module: Module) -> None:
        a = self.ports["io_in_a"]
        b = self.ports["io_in_b"]
        c = self.ports["io_in_c"]
        carry = (a & b) | (a & c) | (b & c)
        module.d.comb += [
            self.ports["io_out_sum"].eq(a ^ b ^ c),
            self.ports["io_out_car"].eq(carry << 1),
        ]

    # Implement the locked bit-paired four-input compressor. / 实现锁定的成对位四输入压缩器。
    def _csa4(self, module: Module) -> None:
        a = self.ports["io_in_a"]
        b = self.ports["io_in_b"]
        c = self.ports["io_in_c"]
        d = self.ports["io_in_d"]
        width = len(a)
        cout = [Mux(a[index] ^ b[index], c[index], a[index]) for index in range(width)]
        raw_sums = []
        raw_carries = []
        for index in range(width):
            prior = Const(0) if index == 0 else cout[index - 1]
            parity = a[index] ^ b[index] ^ c[index] ^ d[index]
            raw_sums.append(parity ^ prior)
            raw_carries.append(Mux(parity, prior, d[index]))
        sums = []
        carries = []
        for index in range(width):
            if index == 0:
                sums.append(raw_sums[index])
                carries.append(Const(0))
            elif index % 2 == 0:
                sums.append(raw_sums[index])
                carries.append(raw_carries[index - 1])
            else:
                sums.append(raw_carries[index - 1])
                carries.append(raw_sums[index])
        module.d.comb += [
            self.ports["io_out_sum"].eq(Cat(*sums)),
            self.ports["io_out_car"].eq(Cat(*carries)),
        ]

    # Implement the eight-entry irrevocable ID allocator. / 实现八项不可撤销 ID 分配器。
    def _id_pool(self, module: Module) -> None:
        p = self.ports
        bitmap = Signal(8, init=0xFF, name="id_bitmap")
        selected = Signal(3, init=0, name="id_selected")
        valid = Signal(init=1, name="id_valid")
        taken = Mux(p["io_alloc_ready"], Const(1, 8) << selected, 0)
        released = Mux(p["io_free_valid"], Const(1, 8) << p["io_free_bits"], 0)
        next_bitmap = (bitmap & ~taken) | released
        count = sum(bitmap[index] for index in range(8))
        next_valid = (bitmap.any() & ~((count == 1) & p["io_alloc_ready"])) | p["io_free_valid"]
        update_select = p["io_alloc_ready"] | (~valid & p["io_free_valid"])
        module.d.comb += [p["io_alloc_valid"].eq(valid), p["io_alloc_bits"].eq(selected)]
        with module.If(p["io_alloc_ready"] | p["io_free_valid"]):
            module.d.sync += [bitmap.eq(next_bitmap), valid.eq(next_valid)]
        with module.If(update_select):
            module.d.sync += selected.eq(_priority_index(next_bitmap, 8))

    # Implement the IEEE 1149.1 TAP state transitions. / 实现 IEEE 1149.1 TAP 状态转移。
    def _jtag_state(self, module: Module) -> None:
        p = self.ports
        state = Signal(4, init=0xF, name="jtag_state")
        tms = p["io_tms"]
        transitions = Array([
            Mux(tms, 5, 2), Mux(tms, 5, 3), Mux(tms, 1, 2), Mux(tms, 0, 3),
            Mux(tms, 15, 14), Mux(tms, 7, 12), Mux(tms, 1, 2), Mux(tms, 4, 6),
            Mux(tms, 13, 10), Mux(tms, 13, 11), Mux(tms, 9, 10), Mux(tms, 8, 11),
            Mux(tms, 7, 12), Mux(tms, 7, 12), Mux(tms, 9, 10), Mux(tms, 15, 12),
        ])
        module.d.sync += state.eq(transitions[state])
        module.d.comb += p["io_currState"].eq(state)

    # Implement one locked Fibonacci LFSR specialization. / 实现一个锁定 Fibonacci LFSR 特化。
    def _lfsr(self, module: Module) -> None:
        p = self.ports
        width = 16 if self.member.endswith("_3") else 15
        state = Signal(width, init=1, name="lfsr_state")
        if width == 16:
            feedback = state[10] ^ state[12] ^ state[13] ^ state[15]
            with module.If(p["io_increment"]):
                module.d.sync += state.eq(Cat(feedback, state[:-1]))
        else:
            feedback = state[13] ^ state[14]
            module.d.sync += state.eq(Cat(feedback, state[:-1]))
        for index in range(width):
            module.d.comb += p[f"io_out_{index}"].eq(state[index])

    # Implement one four-entry overwrite-capable queue specialization. / 实现一个四项可覆盖队列特化。
    def _overrideable_queue(self, module: Module) -> None:
        p = self.ports
        fields = [name.removeprefix("io_in_bits_") for name in p if name.startswith("io_in_bits_")]
        entries = {
            field: Array([
                Signal(len(p[f"io_in_bits_{field}"]), name=f"queue_{field}_{index}", reset_less=True)
                for index in range(4)
            ])
            for field in fields
        }
        valids = Signal(4, init=0, name="queue_valids")
        read_pointer = Signal(2, init=0, name="queue_read_pointer")
        write_pointer = Signal(2, init=0, name="queue_write_pointer")
        out_valid = valids.bit_select(read_pointer, 1)
        fire = out_valid & p["io_out_ready"]
        module.d.comb += p["io_out_valid"].eq(out_valid)
        for field in fields:
            module.d.comb += p[f"io_out_bits_{field}"].eq(entries[field][read_pointer])
        with module.If(fire):
            module.d.sync += [
                valids.bit_select(read_pointer, 1).eq(0),
                read_pointer.eq(read_pointer + 1),
            ]
        with module.If(p["io_in_valid"]):
            for field in fields:
                module.d.sync += entries[field][write_pointer].eq(p[f"io_in_bits_{field}"])
            module.d.sync += [
                valids.bit_select(write_pointer, 1).eq(1),
                write_pointer.eq(write_pointer + 1),
            ]

    # Implement the three-stage time-valid synchronizer and data capture. / 实现三级时间有效同步和数据捕获。
    def _time_async(self, module: Module) -> None:
        p = self.ports
        valid_chain = Signal(3, init=0, name="time_valid_chain")
        delayed_valid = Signal(init=0, name="time_valid_delayed")
        captured_time = Signal(64, init=0, name="time_captured")
        edge = valid_chain[2] ^ delayed_valid
        module.d.sync += [
            valid_chain.eq(Cat(p["io_i_time_valid"], valid_chain[:2])),
            delayed_valid.eq(valid_chain[2]),
        ]
        with module.If(edge):
            module.d.sync += captured_time.eq(p["io_i_time_bits"])
        module.d.comb += p["io_o_time_bits"].eq(captured_time)

    # Implement the fixed-threshold radix-4 quotient selector. / 实现固定阈值 radix-4 商选择器。
    def _qds(self, module: Module) -> None:
        remainder = self.ports["io_rem_i"]
        signs = Cat(
            (remainder + 0x0D)[5],
            (remainder + 0x04)[5],
            (remainder - 0x03)[5],
            (remainder - 0x0C)[5],
        )
        module.d.comb += self.ports["io_quo_dig_o"].eq(_qds_digit(signs))

    # Implement the previous-digit-dependent radix-4 quotient selector. / 实现依赖前一商数字的 radix-4 商选择器。
    def _qds_spec(self, module: Module) -> None:
        p = self.ports
        previous = p["io_prev_quo_dig_i"]
        bases = (
            p["io_rem_i"] + p["io_divisor_mul_neg_2_i"],
            p["io_rem_i"] + p["io_divisor_mul_neg_1_i"],
            p["io_rem_i"],
            p["io_rem_i"] + p["io_divisor_mul_pos_1_i"],
            p["io_rem_i"] + p["io_divisor_mul_pos_2_i"],
        )
        signs: Any = Const(0, 4)
        for index, base in enumerate(bases):
            signs = signs | Mux(previous[index], _qds_sign_window(base), 0)
        module.d.comb += p["io_quo_dig_o"].eq(_qds_digit(signs))

    # Elaborate only source-backed members and keep the rest explicit. / 仅展开有来源依据的成员并显式保留其余合约。
    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        if self.member in _STATEFUL_MEMBERS:
            self._add_sync_domain(module)
        if self.member in {"CSA3to2", "CSA3to2_20", "CSA3to2_24"}:
            self._csa3(module)
        elif self.member == "CSA4to2":
            self._csa4(module)
        elif self.member == "IDPool":
            self._id_pool(module)
        elif self.member == "JtagStateMachine":
            self._jtag_state(module)
        elif self.member in {"MaxPeriodFibonacciLFSR", "MaxPeriodFibonacciLFSR_3"}:
            self._lfsr(module)
        elif self.member in {"OverrideableQueue", "OverrideableQueue_1"}:
            self._overrideable_queue(module)
        elif self.member == "TimeAsync":
            self._time_async(module)
        elif self.member == "r4_qds_v2":
            self._qds(module)
        elif self.member == "r4_qds_v2_spec":
            self._qds_spec(module)
        else:
            for name, direction, width in self.specs:
                if direction == "output":
                    module.d.comb += self.ports[name].eq(Const(0, width))
        return module


# =============================================================================
# Public Adapter
# =============================================================================
# Export one deterministic same-name utility module. / 导出一个确定性的同名工具模块。
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    del injected_dependencies
    member = COVERED_MODULES[0]
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = UtilityResidualFamily(member)
    return verilog.convert(
        top,
        name=member,
        ports=[top.ports[name] for name, _direction, _width in top.specs],
        emit_src=False,
    )


# =============================================================================
# Direct Entry
# =============================================================================
# Print the default utility member. / 打印默认工具成员。
def main() -> None:
    print(build_verilog({"module": COVERED_MODULES[0]}, {}))


if __name__ == "__main__":
    main()
