"""Direct bounded test for Cpu-Memory-Memory.Prefetch.Metadata.Family-Hardware.py."""
from __future__ import annotations
import importlib.util
import unittest
from pathlib import Path
from amaranth import Module, Signal
from amaranth.sim import Simulator

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Cpu-Memory-Memory.Prefetch.Metadata.Family-Hardware.py"
# Load the exact Build subject. / 装载精确 Build 主体。
def load_subject():
    # Avoid any sibling build import. / 避免任何兄弟 Build 导入。
    spec = importlib.util.spec_from_file_location("memory_family_subject", TARGET)
    if spec is None or spec.loader is None: raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
class MemoryFamilyTest(unittest.TestCase):
    # Verify every frozen member exports. / 验证每个冻结成员可导出。
    def test_exact_members_export(self):
        # Iterate the declared family catalog. / 遍历声明的 family catalog。
        module = load_subject()
        for member in module.COVERED_MODULES:
            self.assertIn("module " + member, module.build_verilog({"module": member}, {}))
    # Verify the ten-way PLRU descends through the selected eight-way branch. / 验证十路 PLRU 沿选中八路子树继续译码。
    def test_ten_way_plru_uses_selected_upper_subtree(self):
        # Select way six with state bits in the right subtree. / 用右子树状态位选择第六路。
        subject = load_subject()
        module = Module()
        state = Signal(9)
        way = Signal(4)
        module.d.comb += way.eq(subject._plru_way(state, 10))
        simulator = Simulator(module)

        async def bench(ctx):
            ctx.set(state, 0x61)
            self.assertEqual(ctx.get(way), 6)

        simulator.add_testbench(bench)
        simulator.run()

    # Verify multi-hit encoding follows Chisel OHToUInt's highest-bit priority.
    def test_one_hot_index_matches_oh_to_uint_circuit(self):
        subject = load_subject()
        module = Module()
        matches = Signal(4)
        index = Signal(2)
        module.d.comb += index.eq(subject._one_hot_index(
            [matches[bit] for bit in range(4)], 2))
        simulator = Simulator(module)

        async def bench(ctx):
            for pattern in (0, 1, 2, 3, 5, 9, 10, 15):
                ctx.set(matches, pattern)
                await ctx.delay(1e-9)
                expected = ((2 if pattern & 0xC else 0) |
                            (1 if pattern & 0xA else 0))
                self.assertEqual(ctx.get(index), expected)

        simulator.add_testbench(bench)
        simulator.run()

    def test_ten_entry_index_encodes_all_input_patterns(self):
        subject = load_subject()
        module = Module()
        matches = Signal(10)
        index = Signal(4)
        module.d.comb += index.eq(subject._one_hot_index(
            [matches[bit] for bit in range(10)], 4))
        simulator = Simulator(module)

        async def bench(ctx):
            for pattern in range(1 << 10):
                ctx.set(matches, pattern)
                await ctx.delay(1e-9)
                expected = (8 if pattern & 0x300 else 0)
                expected |= 4 if pattern & 0x0F0 else 0
                expected |= 2 if pattern & 0x0CC else 0
                expected |= 1 if pattern & 0x2AA else 0
                self.assertEqual(ctx.get(index), expected, pattern)

        simulator.add_testbench(bench)
        simulator.run()


if __name__ == "__main__": unittest.main()
