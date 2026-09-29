"""Focused regression for StoreQueueData's lane-slice composition gate."""

from __future__ import annotations

import unittest

from v2_storequeue_composition_validator import (
    COMMON_INPUTS,
    EXPECTED_CHILD_PORTS,
    check_children,
    check_output_coverage,
)


class StoreQueueCompositionTests(unittest.TestCase):
    """Keep all 32 child connections observable to the structural gate."""

    def child_table(self, lane: int) -> dict[str, str]:
        """Build one complete, correctly wired child interface row."""

        row = {name: name for name in COMMON_INPUTS}
        for port in ("io_data_wdata_0", "io_data_wdata_1"):
            row[port] = f"{port}[{lane * 8 + 7}:{lane * 8}]"
        for port in ("io_mask_wdata_0", "io_mask_wdata_1"):
            row[port] = f"{port}[{lane}]"
        row.update({"clock": "clock", "reset": "reset"})
        for forward in range(3):
            row[f"io_forwardValid_{forward}"] = f"io_forwardMask_{forward}_{lane}"
            row[f"io_forwardData_{forward}"] = f"io_forwardData_{forward}_{lane}"
        for read in range(2):
            row[f"io_rdata_{read}_valid"] = f"read_{read}_valid_{lane}"
            row[f"io_rdata_{read}_data"] = f"read_{read}_data_{lane}"
        return row

    def test_write_data_slices_are_checked_on_both_sides(self) -> None:
        row = self.child_table(0)
        self.assertEqual(len(row), 32)
        self.assertEqual(set(row), EXPECTED_CHILD_PORTS)
        for reference in (False, True):
            self.assertEqual(check_children({0: row}, reference)["rows"][0]["errors"], [])
            for port in (
                "io_data_wdata_0", "io_data_wdata_1",
                "io_mask_wdata_0", "io_mask_wdata_1",
            ):
                mutated = dict(row)
                mutated[port] = "wrong_slice"
                errors = check_children({0: mutated}, reference)["rows"][0]["errors"]
                self.assertTrue(any(error.startswith(f"{port}:") for error in errors))

    def test_missing_or_unknown_named_connection_fails_even_at_32_entries(self) -> None:
        row = self.child_table(4)
        row.pop("io_rdata_0_data")
        row["wrong_read_data"] = "read_data_4"

        result = check_children({4: row}, reference=False)

        self.assertEqual(result["rows"][4]["connection_count"], 32)
        self.assertFalse(result["rows"][4]["port_set_exact"])
        self.assertTrue(any(error.startswith("missing_ports=") for error in result["rows"][4]["errors"]))
        self.assertTrue(any(error.startswith("unexpected_ports=") for error in result["rows"][4]["errors"]))

    def test_parent_output_coverage_accounts_for_reads_and_every_forward_lane(self) -> None:
        children = {lane: self.child_table(lane) for lane in range(16)}
        read_rows = [
            {"output": f"io_rdata_{read}_{kind}", "dut_exact": True,
             "reference_exact": True}
            for read in range(2)
            for kind in ("mask", "data")
        ]
        read_assembly = {"rows": read_rows, "all_exact": True}
        output_names = {
            *(row["output"] for row in read_rows),
            *(f"io_forward{kind}_{forward}_{lane}"
              for forward in range(3)
              for kind in ("Mask", "Data")
              for lane in range(16)),
        }
        ports = {name: ("output", 1) for name in output_names}

        result = check_output_coverage(ports, ports, children, children, read_assembly)

        self.assertEqual(result["dut"]["declared_output_count"], 100)
        self.assertEqual(result["dut"]["covered_output_count"], 100)
        self.assertTrue(result["all_outputs_covered"])

        mutated = {lane: dict(row) for lane, row in children.items()}
        mutated[7]["io_forwardData_2"] = "wrong_lane"
        result = check_output_coverage(ports, ports, mutated, children, read_assembly)
        self.assertFalse(result["dut"]["all_outputs_covered"])
        self.assertIn("io_forwardData_2_7", result["dut"]["missing_outputs"])


if __name__ == "__main__":
    unittest.main()
