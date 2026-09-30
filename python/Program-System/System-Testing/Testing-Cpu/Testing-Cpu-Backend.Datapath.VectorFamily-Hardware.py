"""Bounded direct tests for the UHSC V2 vector datapath family.

本测试只验证锁定端口目录、输出 oracle 与三种同名 Verilog 导出；
完整 V2 行为差分由父级闭包另行承担。
"""

from __future__ import annotations

import importlib.util
from itertools import product
import sys
import unittest
from pathlib import Path
from typing import Any

from amaranth.sim import Settle, Simulator


ROOT = Path(__file__).resolve().parents[4]
TARGET = (
    ROOT
    / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
    / "Cpu-Core-Backend.Datapath.VectorFamily-Hardware.py"
)
MEMBERS = (
    "Og2ForVector",
    "VTypeBuffer",
    "VecExcpDataMergeModule",
    "VIAluSrcTypeModule",
    "VIMacSrcTypeModule",
    "VPermSrcTypeModule",
)


def load_subject() -> Any:
    """Load the exact owned Build. / 加载本批精确 Build。"""

    spec = importlib.util.spec_from_file_location("testing_vector_datapath_family", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def vi_alu_reference(op: int, vsew: int, is_ext: int, is_mask: int) -> tuple[int, ...]:
    """Evaluate the locked VIAlu source-type bit-slice equations."""

    fmt = (op >> 7) & 0b11
    sign = (op >> 6) & 1
    x2 = (vsew + 1) & 0b11
    f2 = (vsew - 1) & 0b11
    f4 = (vsew - 2) & 0b11
    f8 = (vsew - 3) & 0b11

    add_fields = (
        (vsew, vsew, vsew),
        (vsew, vsew, x2),
        (x2, vsew, x2),
        (x2, vsew, vsew),
    )[fmt]
    ext_fields = (
        (f2, f2, vsew),
        (f4, f4, vsew),
        (f8, f8, vsew),
        (0, 0, 0),
    )[fmt]

    def source_type(sew: int) -> int:
        return (sign << 2) | sew

    mask_source = (
        source_type(vsew) if fmt in (1, 2) else 0xF if fmt == 3 else 0
    )
    mask_dest = 0 if fmt == 0 else 0xF
    use_add = not is_ext and not is_mask

    add_vs2, add_vs1, add_vd = (source_type(sew) for sew in add_fields)
    ext_vs2, ext_vs1, ext_vd = (source_type(sew) for sew in ext_fields)
    return (
        (mask_source if is_mask else 0)
        | (ext_vs1 if is_ext else 0)
        | (add_vs1 if use_add else 0),
        (mask_source if is_mask else 0)
        | (ext_vs2 if is_ext else 0)
        | (add_vs2 if use_add else 0),
        (mask_dest if is_mask else 0)
        | (ext_vd if is_ext else 0)
        | (add_vd if use_add else 0),
        int((op & 0x3F) == 2 and fmt == 0),
        int((op & 0x3F) == 2 and fmt == 1),
        int((op & 0x3F) == 2 and fmt == 2),
    )


def observe_vi_alu(module: Any, vectors: Any) -> list[tuple[int, ...]]:
    """Simulate VIAluSrcTypeModule for a sequence of public input vectors."""

    dut = module.VIAluSrcTypeModule()
    ports = dut.ports
    outputs: list[tuple[int, ...]] = []
    output_names = (
        "io_out_vs1Type",
        "io_out_vs2Type",
        "io_out_vdType",
        "io_out_isVextF2",
        "io_out_isVextF4",
        "io_out_isVextF8",
    )

    def process():
        for op, vsew, is_ext, is_mask in vectors:
            yield ports["io_in_fuOpType"].eq(op)
            yield ports["io_in_vsew"].eq(vsew)
            yield ports["io_in_isExt"].eq(is_ext)
            yield ports["io_in_isDstMask"].eq(is_mask)
            yield Settle()
            row = []
            for name in output_names:
                row.append(int((yield ports[name])))
            outputs.append(tuple(row))

    simulator = Simulator(dut)
    simulator.add_process(process)
    simulator.run()
    return outputs


class VectorDatapathFamilyTest(unittest.TestCase):
    """Port and deterministic-export tests. / 端口与确定性导出测试。"""

    def test_members_and_output_oracles(self) -> None:
        module = load_subject()
        self.assertEqual(tuple(module.COVERED_MODULES), MEMBERS)
        for member in MEMBERS:
            outputs = module.vector_datapath_model(member)
            expected = {
                name
                for name, direction, _width in module.PORT_SPECS[member]
                if direction == "output"
            }
            self.assertEqual(set(outputs), expected)
            self.assertTrue(all(value == 0 for value in outputs.values()))

    def test_same_name_exports(self) -> None:
        module = load_subject()
        for member in MEMBERS:
            rtl = module.build_verilog({"module": member}, {})
            self.assertIn(f"module {member}", rtl)
            self.assertEqual(rtl, module.build_verilog({"module": member}, {}))

    def test_vi_alu_sat_counterexample_overlap(self) -> None:
        module = load_subject()
        vector = (0x100, 0, 1, 1)
        observed = observe_vi_alu(module, [vector])[0]
        self.assertEqual((1, 1, 0xF, 0, 0, 0), observed)

    def test_vi_alu_exhaustive_8192_input_combinations(self) -> None:
        module = load_subject()
        vectors = list(product(range(512), range(4), range(2), range(2)))
        observed = observe_vi_alu(module, vectors)
        self.assertEqual(len(vectors), len(observed))
        for vector, actual in zip(vectors, observed):
            self.assertEqual(vi_alu_reference(*vector), actual, f"inputs={vector}")


if __name__ == "__main__":
    unittest.main()
