"""Direct bounded test for Build-Cpu.Memory.Mmu.Lsq.Family-Hardware.py."""
from __future__ import annotations
import importlib.util
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Mmu.Lsq.Family-Hardware.py"
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
if __name__ == "__main__": unittest.main()
