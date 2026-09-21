"""Unit checks for the focused JTAG section-5C reference view."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent))
from v2_jtag_reference_view_validator import synthesizable_view  # noqa: E402


class JtagReferenceViewTest(unittest.TestCase):
    """Keep multiline declaration handling conservative and source-counted."""

    def test_locked_jtag_state_machine_multiline_initializer(self) -> None:
        source = Path(__file__).resolve().parent / "reference-sv/JtagStateMachine.sv"
        view, audit = synthesizable_view(source.read_text(encoding="utf-8"), "JtagStateMachine", True)
        self.assertTrue(audit["line_conservation_ok"])
        self.assertTrue(audit["register_update_equations_preserved"])
        self.assertTrue(audit["view_trusted"])
        self.assertEqual(audit["initialized_declarations_hoisted"], ["_GEN"])
        self.assertEqual(audit["code_lines_view"], audit["code_lines_locked"] + 1)
        self.assertNotIn("automatic logic", view)
        self.assertIn("reg [15:0][3:0] _GEN;", view)
        self.assertIn("_GEN =\n{{io_tms ? 4'hF : 4'hC},", view)

    def test_multiline_initializer_keeps_expression_lines(self) -> None:
        source = """module Demo(\n  input clock,\n  input [3:0] data,\n  output out\n);\n  reg q;\n  always @(posedge clock) begin\n    automatic logic [1:0][3:0] lanes;\n    automatic logic [3:0] temporary =\n      data + 4'h1;\n    lanes = {2{data}};\n    q <= temporary[0];\n  end\n  assign out = q;\nendmodule\n"""
        view, audit = synthesizable_view(source, "Demo", False)
        self.assertTrue(audit["view_trusted"])
        self.assertIn("reg [1:0][3:0] lanes;", view)
        self.assertIn("reg [3:0] temporary;", view)
        self.assertIn("temporary =\ndata + 4'h1;", view)
        self.assertEqual(audit["code_lines_view"], audit["code_lines_locked"] + 1)

    def test_locked_jtag_tap_controller_view_is_trusted(self) -> None:
        source = Path(__file__).resolve().parent / "reference-sv/JtagTapController.sv"
        view, audit = synthesizable_view(source.read_text(encoding="utf-8"), "JtagTapController", True)
        self.assertTrue(audit["view_trusted"])
        self.assertEqual(audit["initialized_declarations_hoisted"], [])
        self.assertNotIn("automatic logic", view)
        self.assertIn("module REF_JtagTapController(", view)

    def test_unsupported_assignment_pattern_is_rejected(self) -> None:
        source = """module Demo(input clock, output out);\n  always @(posedge clock) begin\n    automatic logic [3:0] value = '{default: 1'b0};\n    out <= value[0];\n  end\nendmodule\n"""
        with self.assertRaises(AssertionError):
            synthesizable_view(source, "Demo", False)


if __name__ == "__main__":
    unittest.main()
