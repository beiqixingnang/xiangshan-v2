"""Unit checks for the shared strict-family section-5C reference view."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent))
from v2_strict_family_rail import synthesizable_view  # noqa: E402


class StrictFamilyReferenceViewTest(unittest.TestCase):
    """Keep automatic-declaration rewriting lossless and source-counted."""

    def test_locked_pmp_checker_multiline_initializers(self) -> None:
        reference = Path(__file__).resolve().parent / "reference-sv/PMPChecker_2.sv"
        view, audit = synthesizable_view(
            reference.read_text(encoding="utf-8"), "PMPChecker_2", True
        )
        self.assertTrue(audit["line_conservation_ok"])
        self.assertTrue(audit["register_update_equations_preserved"])
        self.assertTrue(audit["view_trusted"])
        self.assertNotIn("automatic logic", view)
        self.assertIn("reg res_pmp_is_match;", view)
        self.assertIn("res_pmp_is_match = \n(io_check_env_pmp_0_cfg_a[1]", view)

    def test_multiline_expression_lines_are_preserved(self) -> None:
        source = """module Demo(
  input clock,
  input [3:0] data,
  output out
);
  reg q;
  always @(posedge clock) begin
    automatic logic [1:0][3:0] lanes;
    automatic logic [3:0] temporary =
      data + 4'h1;
    lanes = {2{data}};
    q <= temporary[0];
  end
  assign out = q;
endmodule
"""
        view, audit = synthesizable_view(source, "Demo", False)
        self.assertTrue(audit["view_trusted"])
        self.assertIn("reg [1:0][3:0]  lanes;", view)
        self.assertIn("reg [3:0]  temporary;", view)
        self.assertIn("temporary = \ndata + 4'h1;", view)
        self.assertEqual(audit["code_lines_view"], audit["code_lines_locked"] + 1)


if __name__ == "__main__":
    unittest.main()
