"""Unit tests for the shared strict family reference-view rail."""

from __future__ import annotations

import unittest

from v2_strict_family_rail import synthesizable_view


class SynthesizableViewTest(unittest.TestCase):
    """Protect source-conserving rewrites used before formal comparison."""

    def test_hoists_multiline_initialized_block_local(self) -> None:
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

        view, audit = synthesizable_view(source, "Demo", rename=False)

        self.assertNotIn("automatic logic", view)
        self.assertIn("reg [1:0][3:0] lanes;", view)
        self.assertIn("reg [3:0] temporary;", view)
        self.assertIn("temporary = \ndata + 4'h1;", view)
        self.assertTrue(audit["line_conservation_ok"])
        self.assertTrue(audit["register_update_equations_preserved"])
        self.assertTrue(audit["view_trusted"])


if __name__ == "__main__":
    unittest.main()
