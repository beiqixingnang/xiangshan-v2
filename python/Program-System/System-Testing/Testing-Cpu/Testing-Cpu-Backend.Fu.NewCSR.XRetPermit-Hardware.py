"""Direct checks for the standalone XRetPermitModule leaf."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from typing import Any

from amaranth.sim import Settle, Simulator


# Module Contract
# Direct import, export and executable privilege-return checks.

# Fixtures And Support
TEST_ID = "Build-Cpu.Backend.Fu.NewCSR.XRetPermit"
SUBJECT_TYPE = "build"
SUBJECT_ID = "Build-Cpu.Backend.Fu.NewCSR.XRetPermit"
DIRECT = True

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Cpu-Core-Backend.Fu.NewCSR.XRetPermit-Hardware.py"
)


def load_subject() -> Any:
    """Load the exact standalone Build path."""

    spec = importlib.util.spec_from_file_location("testing_xret_permit_leaf", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observe(module: Any, values: dict[str, int]) -> dict[str, int]:
    """Evaluate one vector with deterministic zero defaults."""

    dut = module.PermitModule()
    outputs: dict[str, int] = {}

    def process():
        for name, signal in dut.ports.items():
            if name.startswith("io_in_"):
                yield signal.eq(0)
        for name, value in values.items():
            yield dut.ports[name].eq(value)
        yield Settle()
        for name, direction, _width in dut.specs:
            if direction == "output":
                outputs[name] = int((yield dut.ports[name]))

    simulator = Simulator(dut)
    simulator.add_process(process)
    simulator.run()
    return outputs


# Subject Contract
class BuildSubjectContractTest(unittest.TestCase):
    """Check the explicit standalone subject and its public export."""

    def test_subject_contract(self) -> None:
        module = load_subject()
        self.assertEqual(module.COVERED_MODULES, ("XRetPermitModule",))
        self.assertEqual(len(module.__all__), len(set(module.__all__)))
        for name in module.__all__:
            self.assertTrue(hasattr(module, name), name)
        source = TARGET.read_text(encoding="utf-8")
        positions = [source.index("# " + zone) for zone in (
            "Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")]
        self.assertEqual(positions, sorted(positions))
        first = module.build_verilog({"module": "XRetPermitModule"}, {})
        second = module.build_verilog({"module": "XRetPermitModule"}, {})
        self.assertEqual(first, second)
        self.assertIn("module XRetPermitModule", first)


# Behavior Tests
class XRetPermitLeafTest(unittest.TestCase):
    """Check privilege, virtualization, and debug gates."""

    def test_return_permission_vectors(self) -> None:
        module = load_subject()
        legal_mret = observe(module, {
            "io_in_privState_PRVM": 3,
            "io_in_xRet_mret": 1,
        })
        self.assertEqual(legal_mret["io_out_Xret_EX_II"], 0)
        self.assertEqual(legal_mret["io_out_hasLegalMret"], 1)

        trapped_sret = observe(module, {
            "io_in_privState_PRVM": 1,
            "io_in_xRet_sret": 1,
            "io_in_status_tsr": 1,
        })
        self.assertEqual(trapped_sret["io_out_Xret_EX_II"], 1)
        self.assertEqual(trapped_sret["io_out_hasLegalSret"], 0)

        virtual_sret = observe(module, {
            "io_in_privState_PRVM": 1,
            "io_in_privState_V": 1,
            "io_in_xRet_sret": 1,
            "io_in_status_vtsr": 1,
        })
        self.assertEqual(virtual_sret["io_out_Xret_EX_VI"], 1)
        self.assertEqual(virtual_sret["io_out_hasLegalSret"], 0)

        debug_dret = observe(module, {
            "io_in_debugMode": 1,
            "io_in_xRet_dret": 1,
        })
        self.assertEqual(debug_dret["io_out_hasLegalDret"], 1)
