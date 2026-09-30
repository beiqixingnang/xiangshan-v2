#!/usr/bin/env python3
# Module Contract
"""Bounded direct tests for DCache metadata arrays."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from typing import Any

from amaranth.sim import Settle, Simulator, Tick

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Cpu-Memory-Memory.Dcache.MetaArray-Hardware.py"


# Load the exact Build. / 加载精确 Build。
def load_subject() -> Any:
    """Load the metadata aggregate. / 加载元数据聚合。"""

    spec = importlib.util.spec_from_file_location("testing_dcache_meta", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


class DcacheMetaArrayTest(unittest.TestCase):
    """Check staged metadata storage behavior. / 检查分级元数据存储行为。"""

    # Verify all members keep same-name exports. / 验证所有成员保持同名导出。
    def test_all_members_export(self) -> None:
        module = load_subject()
        for member in module.COVERED_MODULES:
            self.assertIn(f"module {member}", module.build_verilog({"module": member}, {}))

    # Verify coherent metadata uses current and delayed write bypass. / 验证一致性元数据使用当前和延迟写旁路。
    def test_coherent_metadata_uses_s0_s1_bypass(self) -> None:
        module = load_subject()
        dut = module.DcacheMetaArrayFamily("L1CohMetaArray")
        observed: list[int] = []

        def process():
            yield dut.reset.eq(1)
            yield Tick()
            yield dut.reset.eq(0)
            yield dut.ports["io_write_0_valid"].eq(1)
            yield dut.ports["io_write_0_bits_idx"].eq(7)
            yield dut.ports["io_write_0_bits_way_en"].eq(1)
            yield dut.ports["io_write_0_bits_meta_coh_state"].eq(3)
            yield dut.ports["io_read_0_valid"].eq(1)
            yield dut.ports["io_read_0_bits_idx"].eq(7)
            yield Tick()
            yield Settle()
            observed.append(int((yield dut.ports["io_resp_0_0_coh_state"])))
            yield dut.ports["io_write_0_valid"].eq(0)
            yield Tick()
            yield Settle()
            observed.append(int((yield dut.ports["io_resp_0_0_coh_state"])))
            yield Tick()
            yield Settle()
            observed.append(int((yield dut.ports["io_resp_0_0_coh_state"])))

        simulator = Simulator(dut)
        simulator.add_clock(1e-6)
        simulator.add_process(process)
        simulator.run()
        self.assertEqual([3, 3, 3], observed)

    # Verify error metadata keeps both fields through the pipeline. / 验证错误元数据在流水线中保持两个字段。
    def test_error_metadata_uses_s0_s1_bypass(self) -> None:
        module = load_subject()
        dut = module.DcacheMetaArrayFamily("L1ErrorMetaArray")
        observed: list[tuple[int, int]] = []

        def process():
            yield dut.reset.eq(1)
            yield Tick()
            yield dut.reset.eq(0)
            yield dut.ports["io_write_0_valid"].eq(1)
            yield dut.ports["io_write_0_bits_idx"].eq(11)
            yield dut.ports["io_write_0_bits_way_en"].eq(4)
            yield dut.ports["io_write_0_bits_error_tl_denied"].eq(1)
            yield dut.ports["io_write_0_bits_error_tl_corrupt"].eq(1)
            yield dut.ports["io_read_1_valid"].eq(1)
            yield dut.ports["io_read_1_bits_idx"].eq(11)
            yield Tick()
            yield Settle()
            observed.append((
                int((yield dut.ports["io_resp_1_2_tl_denied"])),
                int((yield dut.ports["io_resp_1_2_tl_corrupt"])),
            ))
            yield dut.ports["io_write_0_valid"].eq(0)
            yield Tick()
            yield Settle()
            observed.append((
                int((yield dut.ports["io_resp_1_2_tl_denied"])),
                int((yield dut.ports["io_resp_1_2_tl_corrupt"])),
            ))
            yield Tick()
            yield Settle()
            observed.append((
                int((yield dut.ports["io_resp_1_2_tl_denied"])),
                int((yield dut.ports["io_resp_1_2_tl_corrupt"])),
            ))

        simulator = Simulator(dut)
        simulator.add_clock(1e-6)
        simulator.add_process(process)
        simulator.run()
        self.assertEqual([(1, 1), (1, 1), (1, 1)], observed)

    # Verify flag writes use constants before the data-bearing port. / 验证标志写在带数据端口前使用常量。
    def test_flag_write_constants_and_data_latency(self) -> None:
        module = load_subject()
        dut = module.DcacheMetaArrayFamily("L1FlagMetaArray")
        observed: list[tuple[int, int, int, int]] = []

        def sample() -> tuple[int, int, int, int]:
            return (
                int((yield dut.ports["io_resp_3_0"])),
                int((yield dut.ports["io_resp_3_1"])),
                int((yield dut.ports["io_resp_3_2"])),
                int((yield dut.ports["io_resp_3_3"])),
            )

        def process():
            yield dut.reset.eq(1)
            yield Tick()
            yield dut.reset.eq(0)
            yield dut.ports["io_read_3_valid"].eq(1)
            yield dut.ports["io_read_3_bits_idx"].eq(19)
            for write, way_enable in enumerate((1, 2, 4, 8)):
                yield dut.ports[f"io_write_{write}_valid"].eq(1)
                yield dut.ports[f"io_write_{write}_bits_idx"].eq(19)
                yield dut.ports[f"io_write_{write}_bits_way_en"].eq(way_enable)
            yield dut.ports["io_write_3_bits_flag"].eq(1)
            yield Tick()
            yield Settle()
            observed.append((yield from sample()))
            for write in range(4):
                yield dut.ports[f"io_write_{write}_valid"].eq(0)
            yield Tick()
            yield Settle()
            observed.append((yield from sample()))
            yield dut.ports["io_write_3_valid"].eq(1)
            yield dut.ports["io_write_3_bits_idx"].eq(19)
            yield dut.ports["io_write_3_bits_way_en"].eq(8)
            yield dut.ports["io_write_3_bits_flag"].eq(0)
            yield Tick()
            yield Settle()
            observed.append((yield from sample()))
            yield dut.ports["io_write_3_valid"].eq(0)
            yield Tick()
            yield Settle()
            observed.append((yield from sample()))

        simulator = Simulator(dut)
        simulator.add_clock(1e-6)
        simulator.add_process(process)
        simulator.run()
        self.assertEqual(
            [(0, 0, 0, 0), (1, 1, 1, 1), (1, 1, 1, 1), (1, 1, 1, 0)],
            observed,
        )

    # Verify prefetch metadata bypasses only the delayed write stage. / 验证预取元数据只旁路延迟写入级。
    def test_prefetch_write_constants_and_s1_bypass(self) -> None:
        module = load_subject()
        dut = module.DcacheMetaArrayFamily("L1PrefetchSourceArray")
        observed: list[tuple[int, int, int, int]] = []

        def sample() -> tuple[int, int, int, int]:
            return (
                int((yield dut.ports["io_resp_0_0"])),
                int((yield dut.ports["io_resp_0_1"])),
                int((yield dut.ports["io_resp_0_2"])),
                int((yield dut.ports["io_resp_0_3"])),
            )

        def process():
            yield dut.reset.eq(1)
            yield Tick()
            yield dut.reset.eq(0)
            yield dut.ports["io_read_0_valid"].eq(1)
            yield dut.ports["io_read_0_bits_idx"].eq(23)
            for write, way_enable in enumerate((1, 2, 4, 8)):
                yield dut.ports[f"io_write_{write}_valid"].eq(1)
                yield dut.ports[f"io_write_{write}_bits_idx"].eq(23)
                yield dut.ports[f"io_write_{write}_bits_way_en"].eq(way_enable)
            yield dut.ports["io_write_3_bits_source"].eq(6)
            yield Tick()
            yield Settle()
            observed.append((yield from sample()))
            for write in range(4):
                yield dut.ports[f"io_write_{write}_valid"].eq(0)
            yield Tick()
            yield Settle()
            observed.append((yield from sample()))
            yield Tick()
            yield Settle()
            observed.append((yield from sample()))

        simulator = Simulator(dut)
        simulator.add_clock(1e-6)
        simulator.add_process(process)
        simulator.run()
        self.assertEqual([(0, 0, 0, 0), (1, 1, 1, 6), (1, 1, 1, 6)], observed)


if __name__ == "__main__":
    unittest.main()
