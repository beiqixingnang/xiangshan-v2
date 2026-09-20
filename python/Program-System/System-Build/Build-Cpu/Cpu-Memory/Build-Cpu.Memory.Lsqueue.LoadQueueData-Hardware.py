"""UHSC V2 load-queue address and mask storage family.
昆明湖 V2 加载队列地址与掩码存储 family。

The family preserves the locked LqRawDataModule specializations, including
registered reads, bank-independent write priority, and CAM-style address or
mask comparisons.  Four generated members share one source-backed aggregate.
"""

from __future__ import annotations

from typing import Any, cast

from amaranth import Array, ClockDomain, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
__all__ = ["COVERED_MODULES", "LoadQueueDataFamily", "build_verilog", "main"]

COVERED_MODULES: tuple[str, ...] = (
    "LqMaskModule", "LqPAddrModule", "LqPAddrModule_1", "LqVAddrModule",
)



# =============================================================================
# Configuration
# =============================================================================
def lq_mask_specs() -> tuple[tuple[str, str, int], ...]:
    """Return the 32-entry mask-CAM port surface. / 返回 32 项掩码 CAM 端口表面。"""

    ports: list[tuple[str, str, int]] = [("clock", "input", 1), ("reset", "input", 1)]
    for index in range(3):
        ports.extend(((f"io_wen_{index}", "input", 1), (f"io_waddr_{index}", "input", 5),
                      (f"io_wdata_{index}", "input", 16)))
    for cam in range(2):
        ports.append((f"io_violationMdata_{cam}", "input", 16))
    for cam in range(2):
        for entry in range(32):
            ports.append((f"io_violationMmask_{cam}_{entry}", "output", 1))
    return tuple(ports)


def lq_paddr_large_specs() -> tuple[tuple[str, str, int], ...]:
    """Return the 72-entry release-CAM port surface. / 返回 72 项释放 CAM 端口表面。"""

    ports: list[tuple[str, str, int]] = [("clock", "input", 1), ("reset", "input", 1)]
    for index in range(3):
        ports.extend(((f"io_wen_{index}", "input", 1), (f"io_waddr_{index}", "input", 7),
                      (f"io_wdata_{index}", "input", 16)))
    ports.append(("io_releaseMdata_2", "input", 16))
    for entry in range(72):
        ports.append((f"io_releaseMmask_2_{entry}", "output", 1))
    for cam in range(3):
        ports.append((f"io_releaseViolationMdata_{cam}", "input", 16))
    for cam in range(3):
        for entry in range(72):
            ports.append((f"io_releaseViolationMmask_{cam}_{entry}", "output", 1))
    return tuple(ports)


def lq_paddr_small_specs() -> tuple[tuple[str, str, int], ...]:
    """Return the 32-entry physical-address CAM surface. / 返回 32 项物理地址 CAM 表面。"""

    ports: list[tuple[str, str, int]] = [("clock", "input", 1), ("reset", "input", 1)]
    for index in range(3):
        ports.extend(((f"io_wen_{index}", "input", 1), (f"io_waddr_{index}", "input", 5),
                      (f"io_wdata_{index}", "input", 24)))
    for cam in range(2):
        ports.extend(((f"io_violationMdata_{cam}", "input", 24),
                      (f"io_violationCheckLine_{cam}", "input", 1)))
    for cam in range(2):
        for entry in range(32):
            ports.append((f"io_violationMmask_{cam}_{entry}", "output", 1))
    return tuple(ports)


def lq_vaddr_specs() -> tuple[tuple[str, str, int], ...]:
    """Return the 72-entry virtual-address store surface. / 返回 72 项虚拟地址存储表面。"""

    ports: list[tuple[str, str, int]] = [("clock", "input", 1), ("reset", "input", 1)]
    for index in range(3):
        ports.extend(((f"io_ren_{index}", "input", 1), (f"io_raddr_{index}", "input", 7),
                      (f"io_rdata_{index}", "output", 50)))
    for index in range(3):
        ports.extend(((f"io_wen_{index}", "input", 1), (f"io_waddr_{index}", "input", 7),
                      (f"io_wdata_{index}", "input", 50)))
    return tuple(ports)


PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {
    "LqMaskModule": lq_mask_specs(),
    "LqPAddrModule": lq_paddr_large_specs(),
    "LqPAddrModule_1": lq_paddr_small_specs(),
    "LqVAddrModule": lq_vaddr_specs(),
}

PortSpec = tuple[str, str, int]

PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    'LqMaskModule': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_wen_0', 'input', 1),
        ('io_wen_1', 'input', 1),
        ('io_wen_2', 'input', 1),
        ('io_waddr_0', 'input', 5),
        ('io_waddr_1', 'input', 5),
        ('io_waddr_2', 'input', 5),
        ('io_wdata_0', 'input', 16),
        ('io_wdata_1', 'input', 16),
        ('io_wdata_2', 'input', 16),
        ('io_violationMdata_0', 'input', 16),
        ('io_violationMdata_1', 'input', 16),
        ('io_violationMmask_0_0', 'output', 1),
        ('io_violationMmask_0_1', 'output', 1),
        ('io_violationMmask_0_2', 'output', 1),
        ('io_violationMmask_0_3', 'output', 1),
        ('io_violationMmask_0_4', 'output', 1),
        ('io_violationMmask_0_5', 'output', 1),
        ('io_violationMmask_0_6', 'output', 1),
        ('io_violationMmask_0_7', 'output', 1),
        ('io_violationMmask_0_8', 'output', 1),
        ('io_violationMmask_0_9', 'output', 1),
        ('io_violationMmask_0_10', 'output', 1),
        ('io_violationMmask_0_11', 'output', 1),
        ('io_violationMmask_0_12', 'output', 1),
        ('io_violationMmask_0_13', 'output', 1),
        ('io_violationMmask_0_14', 'output', 1),
        ('io_violationMmask_0_15', 'output', 1),
        ('io_violationMmask_0_16', 'output', 1),
        ('io_violationMmask_0_17', 'output', 1),
        ('io_violationMmask_0_18', 'output', 1),
        ('io_violationMmask_0_19', 'output', 1),
        ('io_violationMmask_0_20', 'output', 1),
        ('io_violationMmask_0_21', 'output', 1),
        ('io_violationMmask_0_22', 'output', 1),
        ('io_violationMmask_0_23', 'output', 1),
        ('io_violationMmask_0_24', 'output', 1),
        ('io_violationMmask_0_25', 'output', 1),
        ('io_violationMmask_0_26', 'output', 1),
        ('io_violationMmask_0_27', 'output', 1),
        ('io_violationMmask_0_28', 'output', 1),
        ('io_violationMmask_0_29', 'output', 1),
        ('io_violationMmask_0_30', 'output', 1),
        ('io_violationMmask_0_31', 'output', 1),
        ('io_violationMmask_1_0', 'output', 1),
        ('io_violationMmask_1_1', 'output', 1),
        ('io_violationMmask_1_2', 'output', 1),
        ('io_violationMmask_1_3', 'output', 1),
        ('io_violationMmask_1_4', 'output', 1),
        ('io_violationMmask_1_5', 'output', 1),
        ('io_violationMmask_1_6', 'output', 1),
        ('io_violationMmask_1_7', 'output', 1),
        ('io_violationMmask_1_8', 'output', 1),
        ('io_violationMmask_1_9', 'output', 1),
        ('io_violationMmask_1_10', 'output', 1),
        ('io_violationMmask_1_11', 'output', 1),
        ('io_violationMmask_1_12', 'output', 1),
        ('io_violationMmask_1_13', 'output', 1),
        ('io_violationMmask_1_14', 'output', 1),
        ('io_violationMmask_1_15', 'output', 1),
        ('io_violationMmask_1_16', 'output', 1),
        ('io_violationMmask_1_17', 'output', 1),
        ('io_violationMmask_1_18', 'output', 1),
        ('io_violationMmask_1_19', 'output', 1),
        ('io_violationMmask_1_20', 'output', 1),
        ('io_violationMmask_1_21', 'output', 1),
        ('io_violationMmask_1_22', 'output', 1),
        ('io_violationMmask_1_23', 'output', 1),
        ('io_violationMmask_1_24', 'output', 1),
        ('io_violationMmask_1_25', 'output', 1),
        ('io_violationMmask_1_26', 'output', 1),
        ('io_violationMmask_1_27', 'output', 1),
        ('io_violationMmask_1_28', 'output', 1),
        ('io_violationMmask_1_29', 'output', 1),
        ('io_violationMmask_1_30', 'output', 1),
        ('io_violationMmask_1_31', 'output', 1),
    ),
    'LqPAddrModule': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_wen_0', 'input', 1),
        ('io_wen_1', 'input', 1),
        ('io_wen_2', 'input', 1),
        ('io_waddr_0', 'input', 7),
        ('io_waddr_1', 'input', 7),
        ('io_waddr_2', 'input', 7),
        ('io_wdata_0', 'input', 16),
        ('io_wdata_1', 'input', 16),
        ('io_wdata_2', 'input', 16),
        ('io_releaseMdata_2', 'input', 16),
        ('io_releaseMmask_2_0', 'output', 1),
        ('io_releaseMmask_2_1', 'output', 1),
        ('io_releaseMmask_2_2', 'output', 1),
        ('io_releaseMmask_2_3', 'output', 1),
        ('io_releaseMmask_2_4', 'output', 1),
        ('io_releaseMmask_2_5', 'output', 1),
        ('io_releaseMmask_2_6', 'output', 1),
        ('io_releaseMmask_2_7', 'output', 1),
        ('io_releaseMmask_2_8', 'output', 1),
        ('io_releaseMmask_2_9', 'output', 1),
        ('io_releaseMmask_2_10', 'output', 1),
        ('io_releaseMmask_2_11', 'output', 1),
        ('io_releaseMmask_2_12', 'output', 1),
        ('io_releaseMmask_2_13', 'output', 1),
        ('io_releaseMmask_2_14', 'output', 1),
        ('io_releaseMmask_2_15', 'output', 1),
        ('io_releaseMmask_2_16', 'output', 1),
        ('io_releaseMmask_2_17', 'output', 1),
        ('io_releaseMmask_2_18', 'output', 1),
        ('io_releaseMmask_2_19', 'output', 1),
        ('io_releaseMmask_2_20', 'output', 1),
        ('io_releaseMmask_2_21', 'output', 1),
        ('io_releaseMmask_2_22', 'output', 1),
        ('io_releaseMmask_2_23', 'output', 1),
        ('io_releaseMmask_2_24', 'output', 1),
        ('io_releaseMmask_2_25', 'output', 1),
        ('io_releaseMmask_2_26', 'output', 1),
        ('io_releaseMmask_2_27', 'output', 1),
        ('io_releaseMmask_2_28', 'output', 1),
        ('io_releaseMmask_2_29', 'output', 1),
        ('io_releaseMmask_2_30', 'output', 1),
        ('io_releaseMmask_2_31', 'output', 1),
        ('io_releaseMmask_2_32', 'output', 1),
        ('io_releaseMmask_2_33', 'output', 1),
        ('io_releaseMmask_2_34', 'output', 1),
        ('io_releaseMmask_2_35', 'output', 1),
        ('io_releaseMmask_2_36', 'output', 1),
        ('io_releaseMmask_2_37', 'output', 1),
        ('io_releaseMmask_2_38', 'output', 1),
        ('io_releaseMmask_2_39', 'output', 1),
        ('io_releaseMmask_2_40', 'output', 1),
        ('io_releaseMmask_2_41', 'output', 1),
        ('io_releaseMmask_2_42', 'output', 1),
        ('io_releaseMmask_2_43', 'output', 1),
        ('io_releaseMmask_2_44', 'output', 1),
        ('io_releaseMmask_2_45', 'output', 1),
        ('io_releaseMmask_2_46', 'output', 1),
        ('io_releaseMmask_2_47', 'output', 1),
        ('io_releaseMmask_2_48', 'output', 1),
        ('io_releaseMmask_2_49', 'output', 1),
        ('io_releaseMmask_2_50', 'output', 1),
        ('io_releaseMmask_2_51', 'output', 1),
        ('io_releaseMmask_2_52', 'output', 1),
        ('io_releaseMmask_2_53', 'output', 1),
        ('io_releaseMmask_2_54', 'output', 1),
        ('io_releaseMmask_2_55', 'output', 1),
        ('io_releaseMmask_2_56', 'output', 1),
        ('io_releaseMmask_2_57', 'output', 1),
        ('io_releaseMmask_2_58', 'output', 1),
        ('io_releaseMmask_2_59', 'output', 1),
        ('io_releaseMmask_2_60', 'output', 1),
        ('io_releaseMmask_2_61', 'output', 1),
        ('io_releaseMmask_2_62', 'output', 1),
        ('io_releaseMmask_2_63', 'output', 1),
        ('io_releaseMmask_2_64', 'output', 1),
        ('io_releaseMmask_2_65', 'output', 1),
        ('io_releaseMmask_2_66', 'output', 1),
        ('io_releaseMmask_2_67', 'output', 1),
        ('io_releaseMmask_2_68', 'output', 1),
        ('io_releaseMmask_2_69', 'output', 1),
        ('io_releaseMmask_2_70', 'output', 1),
        ('io_releaseMmask_2_71', 'output', 1),
        ('io_releaseViolationMdata_0', 'input', 16),
        ('io_releaseViolationMdata_1', 'input', 16),
        ('io_releaseViolationMdata_2', 'input', 16),
        ('io_releaseViolationMmask_0_0', 'output', 1),
        ('io_releaseViolationMmask_0_1', 'output', 1),
        ('io_releaseViolationMmask_0_2', 'output', 1),
        ('io_releaseViolationMmask_0_3', 'output', 1),
        ('io_releaseViolationMmask_0_4', 'output', 1),
        ('io_releaseViolationMmask_0_5', 'output', 1),
        ('io_releaseViolationMmask_0_6', 'output', 1),
        ('io_releaseViolationMmask_0_7', 'output', 1),
        ('io_releaseViolationMmask_0_8', 'output', 1),
        ('io_releaseViolationMmask_0_9', 'output', 1),
        ('io_releaseViolationMmask_0_10', 'output', 1),
        ('io_releaseViolationMmask_0_11', 'output', 1),
        ('io_releaseViolationMmask_0_12', 'output', 1),
        ('io_releaseViolationMmask_0_13', 'output', 1),
        ('io_releaseViolationMmask_0_14', 'output', 1),
        ('io_releaseViolationMmask_0_15', 'output', 1),
        ('io_releaseViolationMmask_0_16', 'output', 1),
        ('io_releaseViolationMmask_0_17', 'output', 1),
        ('io_releaseViolationMmask_0_18', 'output', 1),
        ('io_releaseViolationMmask_0_19', 'output', 1),
        ('io_releaseViolationMmask_0_20', 'output', 1),
        ('io_releaseViolationMmask_0_21', 'output', 1),
        ('io_releaseViolationMmask_0_22', 'output', 1),
        ('io_releaseViolationMmask_0_23', 'output', 1),
        ('io_releaseViolationMmask_0_24', 'output', 1),
        ('io_releaseViolationMmask_0_25', 'output', 1),
        ('io_releaseViolationMmask_0_26', 'output', 1),
        ('io_releaseViolationMmask_0_27', 'output', 1),
        ('io_releaseViolationMmask_0_28', 'output', 1),
        ('io_releaseViolationMmask_0_29', 'output', 1),
        ('io_releaseViolationMmask_0_30', 'output', 1),
        ('io_releaseViolationMmask_0_31', 'output', 1),
        ('io_releaseViolationMmask_0_32', 'output', 1),
        ('io_releaseViolationMmask_0_33', 'output', 1),
        ('io_releaseViolationMmask_0_34', 'output', 1),
        ('io_releaseViolationMmask_0_35', 'output', 1),
        ('io_releaseViolationMmask_0_36', 'output', 1),
        ('io_releaseViolationMmask_0_37', 'output', 1),
        ('io_releaseViolationMmask_0_38', 'output', 1),
        ('io_releaseViolationMmask_0_39', 'output', 1),
        ('io_releaseViolationMmask_0_40', 'output', 1),
        ('io_releaseViolationMmask_0_41', 'output', 1),
        ('io_releaseViolationMmask_0_42', 'output', 1),
        ('io_releaseViolationMmask_0_43', 'output', 1),
        ('io_releaseViolationMmask_0_44', 'output', 1),
        ('io_releaseViolationMmask_0_45', 'output', 1),
        ('io_releaseViolationMmask_0_46', 'output', 1),
        ('io_releaseViolationMmask_0_47', 'output', 1),
        ('io_releaseViolationMmask_0_48', 'output', 1),
        ('io_releaseViolationMmask_0_49', 'output', 1),
        ('io_releaseViolationMmask_0_50', 'output', 1),
        ('io_releaseViolationMmask_0_51', 'output', 1),
        ('io_releaseViolationMmask_0_52', 'output', 1),
        ('io_releaseViolationMmask_0_53', 'output', 1),
        ('io_releaseViolationMmask_0_54', 'output', 1),
        ('io_releaseViolationMmask_0_55', 'output', 1),
        ('io_releaseViolationMmask_0_56', 'output', 1),
        ('io_releaseViolationMmask_0_57', 'output', 1),
        ('io_releaseViolationMmask_0_58', 'output', 1),
        ('io_releaseViolationMmask_0_59', 'output', 1),
        ('io_releaseViolationMmask_0_60', 'output', 1),
        ('io_releaseViolationMmask_0_61', 'output', 1),
        ('io_releaseViolationMmask_0_62', 'output', 1),
        ('io_releaseViolationMmask_0_63', 'output', 1),
        ('io_releaseViolationMmask_0_64', 'output', 1),
        ('io_releaseViolationMmask_0_65', 'output', 1),
        ('io_releaseViolationMmask_0_66', 'output', 1),
        ('io_releaseViolationMmask_0_67', 'output', 1),
        ('io_releaseViolationMmask_0_68', 'output', 1),
        ('io_releaseViolationMmask_0_69', 'output', 1),
        ('io_releaseViolationMmask_0_70', 'output', 1),
        ('io_releaseViolationMmask_0_71', 'output', 1),
        ('io_releaseViolationMmask_1_0', 'output', 1),
        ('io_releaseViolationMmask_1_1', 'output', 1),
        ('io_releaseViolationMmask_1_2', 'output', 1),
        ('io_releaseViolationMmask_1_3', 'output', 1),
        ('io_releaseViolationMmask_1_4', 'output', 1),
        ('io_releaseViolationMmask_1_5', 'output', 1),
        ('io_releaseViolationMmask_1_6', 'output', 1),
        ('io_releaseViolationMmask_1_7', 'output', 1),
        ('io_releaseViolationMmask_1_8', 'output', 1),
        ('io_releaseViolationMmask_1_9', 'output', 1),
        ('io_releaseViolationMmask_1_10', 'output', 1),
        ('io_releaseViolationMmask_1_11', 'output', 1),
        ('io_releaseViolationMmask_1_12', 'output', 1),
        ('io_releaseViolationMmask_1_13', 'output', 1),
        ('io_releaseViolationMmask_1_14', 'output', 1),
        ('io_releaseViolationMmask_1_15', 'output', 1),
        ('io_releaseViolationMmask_1_16', 'output', 1),
        ('io_releaseViolationMmask_1_17', 'output', 1),
        ('io_releaseViolationMmask_1_18', 'output', 1),
        ('io_releaseViolationMmask_1_19', 'output', 1),
        ('io_releaseViolationMmask_1_20', 'output', 1),
        ('io_releaseViolationMmask_1_21', 'output', 1),
        ('io_releaseViolationMmask_1_22', 'output', 1),
        ('io_releaseViolationMmask_1_23', 'output', 1),
        ('io_releaseViolationMmask_1_24', 'output', 1),
        ('io_releaseViolationMmask_1_25', 'output', 1),
        ('io_releaseViolationMmask_1_26', 'output', 1),
        ('io_releaseViolationMmask_1_27', 'output', 1),
        ('io_releaseViolationMmask_1_28', 'output', 1),
        ('io_releaseViolationMmask_1_29', 'output', 1),
        ('io_releaseViolationMmask_1_30', 'output', 1),
        ('io_releaseViolationMmask_1_31', 'output', 1),
        ('io_releaseViolationMmask_1_32', 'output', 1),
        ('io_releaseViolationMmask_1_33', 'output', 1),
        ('io_releaseViolationMmask_1_34', 'output', 1),
        ('io_releaseViolationMmask_1_35', 'output', 1),
        ('io_releaseViolationMmask_1_36', 'output', 1),
        ('io_releaseViolationMmask_1_37', 'output', 1),
        ('io_releaseViolationMmask_1_38', 'output', 1),
        ('io_releaseViolationMmask_1_39', 'output', 1),
        ('io_releaseViolationMmask_1_40', 'output', 1),
        ('io_releaseViolationMmask_1_41', 'output', 1),
        ('io_releaseViolationMmask_1_42', 'output', 1),
        ('io_releaseViolationMmask_1_43', 'output', 1),
        ('io_releaseViolationMmask_1_44', 'output', 1),
        ('io_releaseViolationMmask_1_45', 'output', 1),
        ('io_releaseViolationMmask_1_46', 'output', 1),
        ('io_releaseViolationMmask_1_47', 'output', 1),
        ('io_releaseViolationMmask_1_48', 'output', 1),
        ('io_releaseViolationMmask_1_49', 'output', 1),
        ('io_releaseViolationMmask_1_50', 'output', 1),
        ('io_releaseViolationMmask_1_51', 'output', 1),
        ('io_releaseViolationMmask_1_52', 'output', 1),
        ('io_releaseViolationMmask_1_53', 'output', 1),
        ('io_releaseViolationMmask_1_54', 'output', 1),
        ('io_releaseViolationMmask_1_55', 'output', 1),
        ('io_releaseViolationMmask_1_56', 'output', 1),
        ('io_releaseViolationMmask_1_57', 'output', 1),
        ('io_releaseViolationMmask_1_58', 'output', 1),
        ('io_releaseViolationMmask_1_59', 'output', 1),
        ('io_releaseViolationMmask_1_60', 'output', 1),
        ('io_releaseViolationMmask_1_61', 'output', 1),
        ('io_releaseViolationMmask_1_62', 'output', 1),
        ('io_releaseViolationMmask_1_63', 'output', 1),
        ('io_releaseViolationMmask_1_64', 'output', 1),
        ('io_releaseViolationMmask_1_65', 'output', 1),
        ('io_releaseViolationMmask_1_66', 'output', 1),
        ('io_releaseViolationMmask_1_67', 'output', 1),
        ('io_releaseViolationMmask_1_68', 'output', 1),
        ('io_releaseViolationMmask_1_69', 'output', 1),
        ('io_releaseViolationMmask_1_70', 'output', 1),
        ('io_releaseViolationMmask_1_71', 'output', 1),
        ('io_releaseViolationMmask_2_0', 'output', 1),
        ('io_releaseViolationMmask_2_1', 'output', 1),
        ('io_releaseViolationMmask_2_2', 'output', 1),
        ('io_releaseViolationMmask_2_3', 'output', 1),
        ('io_releaseViolationMmask_2_4', 'output', 1),
        ('io_releaseViolationMmask_2_5', 'output', 1),
        ('io_releaseViolationMmask_2_6', 'output', 1),
        ('io_releaseViolationMmask_2_7', 'output', 1),
        ('io_releaseViolationMmask_2_8', 'output', 1),
        ('io_releaseViolationMmask_2_9', 'output', 1),
        ('io_releaseViolationMmask_2_10', 'output', 1),
        ('io_releaseViolationMmask_2_11', 'output', 1),
        ('io_releaseViolationMmask_2_12', 'output', 1),
        ('io_releaseViolationMmask_2_13', 'output', 1),
        ('io_releaseViolationMmask_2_14', 'output', 1),
        ('io_releaseViolationMmask_2_15', 'output', 1),
        ('io_releaseViolationMmask_2_16', 'output', 1),
        ('io_releaseViolationMmask_2_17', 'output', 1),
        ('io_releaseViolationMmask_2_18', 'output', 1),
        ('io_releaseViolationMmask_2_19', 'output', 1),
        ('io_releaseViolationMmask_2_20', 'output', 1),
        ('io_releaseViolationMmask_2_21', 'output', 1),
        ('io_releaseViolationMmask_2_22', 'output', 1),
        ('io_releaseViolationMmask_2_23', 'output', 1),
        ('io_releaseViolationMmask_2_24', 'output', 1),
        ('io_releaseViolationMmask_2_25', 'output', 1),
        ('io_releaseViolationMmask_2_26', 'output', 1),
        ('io_releaseViolationMmask_2_27', 'output', 1),
        ('io_releaseViolationMmask_2_28', 'output', 1),
        ('io_releaseViolationMmask_2_29', 'output', 1),
        ('io_releaseViolationMmask_2_30', 'output', 1),
        ('io_releaseViolationMmask_2_31', 'output', 1),
        ('io_releaseViolationMmask_2_32', 'output', 1),
        ('io_releaseViolationMmask_2_33', 'output', 1),
        ('io_releaseViolationMmask_2_34', 'output', 1),
        ('io_releaseViolationMmask_2_35', 'output', 1),
        ('io_releaseViolationMmask_2_36', 'output', 1),
        ('io_releaseViolationMmask_2_37', 'output', 1),
        ('io_releaseViolationMmask_2_38', 'output', 1),
        ('io_releaseViolationMmask_2_39', 'output', 1),
        ('io_releaseViolationMmask_2_40', 'output', 1),
        ('io_releaseViolationMmask_2_41', 'output', 1),
        ('io_releaseViolationMmask_2_42', 'output', 1),
        ('io_releaseViolationMmask_2_43', 'output', 1),
        ('io_releaseViolationMmask_2_44', 'output', 1),
        ('io_releaseViolationMmask_2_45', 'output', 1),
        ('io_releaseViolationMmask_2_46', 'output', 1),
        ('io_releaseViolationMmask_2_47', 'output', 1),
        ('io_releaseViolationMmask_2_48', 'output', 1),
        ('io_releaseViolationMmask_2_49', 'output', 1),
        ('io_releaseViolationMmask_2_50', 'output', 1),
        ('io_releaseViolationMmask_2_51', 'output', 1),
        ('io_releaseViolationMmask_2_52', 'output', 1),
        ('io_releaseViolationMmask_2_53', 'output', 1),
        ('io_releaseViolationMmask_2_54', 'output', 1),
        ('io_releaseViolationMmask_2_55', 'output', 1),
        ('io_releaseViolationMmask_2_56', 'output', 1),
        ('io_releaseViolationMmask_2_57', 'output', 1),
        ('io_releaseViolationMmask_2_58', 'output', 1),
        ('io_releaseViolationMmask_2_59', 'output', 1),
        ('io_releaseViolationMmask_2_60', 'output', 1),
        ('io_releaseViolationMmask_2_61', 'output', 1),
        ('io_releaseViolationMmask_2_62', 'output', 1),
        ('io_releaseViolationMmask_2_63', 'output', 1),
        ('io_releaseViolationMmask_2_64', 'output', 1),
        ('io_releaseViolationMmask_2_65', 'output', 1),
        ('io_releaseViolationMmask_2_66', 'output', 1),
        ('io_releaseViolationMmask_2_67', 'output', 1),
        ('io_releaseViolationMmask_2_68', 'output', 1),
        ('io_releaseViolationMmask_2_69', 'output', 1),
        ('io_releaseViolationMmask_2_70', 'output', 1),
        ('io_releaseViolationMmask_2_71', 'output', 1),
    ),
    'LqPAddrModule_1': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_wen_0', 'input', 1),
        ('io_wen_1', 'input', 1),
        ('io_wen_2', 'input', 1),
        ('io_waddr_0', 'input', 5),
        ('io_waddr_1', 'input', 5),
        ('io_waddr_2', 'input', 5),
        ('io_wdata_0', 'input', 24),
        ('io_wdata_1', 'input', 24),
        ('io_wdata_2', 'input', 24),
        ('io_violationMdata_0', 'input', 24),
        ('io_violationMdata_1', 'input', 24),
        ('io_violationCheckLine_0', 'input', 1),
        ('io_violationCheckLine_1', 'input', 1),
        ('io_violationMmask_0_0', 'output', 1),
        ('io_violationMmask_0_1', 'output', 1),
        ('io_violationMmask_0_2', 'output', 1),
        ('io_violationMmask_0_3', 'output', 1),
        ('io_violationMmask_0_4', 'output', 1),
        ('io_violationMmask_0_5', 'output', 1),
        ('io_violationMmask_0_6', 'output', 1),
        ('io_violationMmask_0_7', 'output', 1),
        ('io_violationMmask_0_8', 'output', 1),
        ('io_violationMmask_0_9', 'output', 1),
        ('io_violationMmask_0_10', 'output', 1),
        ('io_violationMmask_0_11', 'output', 1),
        ('io_violationMmask_0_12', 'output', 1),
        ('io_violationMmask_0_13', 'output', 1),
        ('io_violationMmask_0_14', 'output', 1),
        ('io_violationMmask_0_15', 'output', 1),
        ('io_violationMmask_0_16', 'output', 1),
        ('io_violationMmask_0_17', 'output', 1),
        ('io_violationMmask_0_18', 'output', 1),
        ('io_violationMmask_0_19', 'output', 1),
        ('io_violationMmask_0_20', 'output', 1),
        ('io_violationMmask_0_21', 'output', 1),
        ('io_violationMmask_0_22', 'output', 1),
        ('io_violationMmask_0_23', 'output', 1),
        ('io_violationMmask_0_24', 'output', 1),
        ('io_violationMmask_0_25', 'output', 1),
        ('io_violationMmask_0_26', 'output', 1),
        ('io_violationMmask_0_27', 'output', 1),
        ('io_violationMmask_0_28', 'output', 1),
        ('io_violationMmask_0_29', 'output', 1),
        ('io_violationMmask_0_30', 'output', 1),
        ('io_violationMmask_0_31', 'output', 1),
        ('io_violationMmask_1_0', 'output', 1),
        ('io_violationMmask_1_1', 'output', 1),
        ('io_violationMmask_1_2', 'output', 1),
        ('io_violationMmask_1_3', 'output', 1),
        ('io_violationMmask_1_4', 'output', 1),
        ('io_violationMmask_1_5', 'output', 1),
        ('io_violationMmask_1_6', 'output', 1),
        ('io_violationMmask_1_7', 'output', 1),
        ('io_violationMmask_1_8', 'output', 1),
        ('io_violationMmask_1_9', 'output', 1),
        ('io_violationMmask_1_10', 'output', 1),
        ('io_violationMmask_1_11', 'output', 1),
        ('io_violationMmask_1_12', 'output', 1),
        ('io_violationMmask_1_13', 'output', 1),
        ('io_violationMmask_1_14', 'output', 1),
        ('io_violationMmask_1_15', 'output', 1),
        ('io_violationMmask_1_16', 'output', 1),
        ('io_violationMmask_1_17', 'output', 1),
        ('io_violationMmask_1_18', 'output', 1),
        ('io_violationMmask_1_19', 'output', 1),
        ('io_violationMmask_1_20', 'output', 1),
        ('io_violationMmask_1_21', 'output', 1),
        ('io_violationMmask_1_22', 'output', 1),
        ('io_violationMmask_1_23', 'output', 1),
        ('io_violationMmask_1_24', 'output', 1),
        ('io_violationMmask_1_25', 'output', 1),
        ('io_violationMmask_1_26', 'output', 1),
        ('io_violationMmask_1_27', 'output', 1),
        ('io_violationMmask_1_28', 'output', 1),
        ('io_violationMmask_1_29', 'output', 1),
        ('io_violationMmask_1_30', 'output', 1),
        ('io_violationMmask_1_31', 'output', 1),
    ),
    'LqVAddrModule': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_ren_0', 'input', 1),
        ('io_ren_1', 'input', 1),
        ('io_ren_2', 'input', 1),
        ('io_raddr_0', 'input', 7),
        ('io_raddr_1', 'input', 7),
        ('io_raddr_2', 'input', 7),
        ('io_rdata_0', 'output', 50),
        ('io_rdata_1', 'output', 50),
        ('io_rdata_2', 'output', 50),
        ('io_wen_0', 'input', 1),
        ('io_wen_1', 'input', 1),
        ('io_wen_2', 'input', 1),
        ('io_waddr_0', 'input', 7),
        ('io_waddr_1', 'input', 7),
        ('io_waddr_2', 'input', 7),
        ('io_wdata_0', 'input', 50),
        ('io_wdata_1', 'input', 50),
        ('io_wdata_2', 'input', 50),
    ),
}

MEMORY_CONFIG: dict[str, tuple[int, int, int]] = {
    "LqMaskModule": (32, 16, 5),
    "LqPAddrModule": (72, 16, 7),
    "LqPAddrModule_1": (32, 24, 5),
    "LqVAddrModule": (72, 50, 7),
}


# =============================================================================
# Implementation
# =============================================================================
class LoadQueueDataFamily(Elaboratable):
    """One load-queue data specialization. / 一个加载队列数据特化。"""

    def __init__(self, member: str = "LqVAddrModule") -> None:
        """Declare the selected locked port surface. / 声明选定的锁定端口表面。"""

        if member not in PORT_SPECS:
            raise ValueError(f"unsupported load-queue member: {member}")
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports: dict[str, Signal] = {
            name: Signal(width, name=name) for name, _direction, width in self.specs
        }
        self.clock = self.ports["clock"]
        self.reset = self.ports["reset"]

    # Elaborate common writes and specialization-specific observations. /
    # 展开共用写入和特化观测逻辑。
    def elaborate(self, platform: Any) -> Module:
        """Build registered reads and CAM equations. / 构建寄存读取与 CAM 方程。"""

        del platform
        module = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.clock
        domain.rst = self.reset
        module.domains += domain
        entries, data_width, address_width = MEMORY_CONFIG[self.member]
        memory = Array(Signal(data_width, name=f"entry_{index}", reset_less=True)
                       for index in range(entries))

        for write in range(3):
            with cast(Any, module.If(self.ports[f"io_wen_{write}"])):
                module.d.sync += memory[self.ports[f"io_waddr_{write}"]].eq(
                    self.ports[f"io_wdata_{write}"]
                )

        if self.member == "LqVAddrModule":
            for read in range(3):
                address = Signal(address_width, name=f"read_address_{read}")
                with cast(Any, module.If(self.ports[f"io_ren_{read}"])):
                    module.d.sync += address.eq(self.ports[f"io_raddr_{read}"])
                module.d.comb += self.ports[f"io_rdata_{read}"].eq(memory[address])
        elif self.member == "LqMaskModule":
            for cam in range(2):
                query = self.ports[f"io_violationMdata_{cam}"]
                for entry in range(entries):
                    module.d.comb += self.ports[f"io_violationMmask_{cam}_{entry}"].eq(
                        (query & memory[entry]) != 0
                    )
        elif self.member == "LqPAddrModule_1":
            for cam in range(2):
                query = self.ports[f"io_violationMdata_{cam}"]
                check_line = self.ports[f"io_violationCheckLine_{cam}"]
                for entry in range(entries):
                    exact = query == memory[entry]
                    cache_line = query[4:data_width] == memory[entry][4:data_width]
                    module.d.comb += self.ports[f"io_violationMmask_{cam}_{entry}"].eq(
                        Mux(check_line, cache_line, exact)
                    )
        else:
            release = self.ports["io_releaseMdata_2"]
            for entry in range(entries):
                module.d.comb += self.ports[f"io_releaseMmask_2_{entry}"].eq(
                    release == memory[entry]
                )
            for cam in range(3):
                query = self.ports[f"io_releaseViolationMdata_{cam}"]
                for entry in range(entries):
                    module.d.comb += self.ports[f"io_releaseViolationMmask_{cam}_{entry}"].eq(
                        query == memory[entry]
                    )
        return module


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    """Export one deterministic same-name load-queue member. / 导出确定性的同名加载队列成员。"""

    del injected_dependencies
    member = "LqVAddrModule"
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = LoadQueueDataFamily(member)
    return verilog.convert(top, name=member, ports=[top.ports[n] for n, _d, _w in top.specs], emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the default load-queue member. / 打印默认加载队列成员。"""

    print(build_verilog({"module": "LqVAddrModule"}, {}))


if __name__ == "__main__":
    main()
