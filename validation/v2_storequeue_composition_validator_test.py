"""Focused regression for StoreQueueData's lane-slice composition gate."""

from __future__ import annotations

import unittest

from v2_storequeue_composition_validator import COMMON_INPUTS, check_children


class StoreQueueCompositionTests(unittest.TestCase):
    """Keep all 32 child connections observable to the structural gate."""

    def test_write_data_slices_are_checked_on_both_sides(self) -> None:
        row = {name: name for name in COMMON_INPUTS}
        for port in ("io_data_wdata_0", "io_data_wdata_1"):
            row[port] = f"{port}[7:0]"
        for port in ("io_mask_wdata_0", "io_mask_wdata_1"):
            row[port] = f"{port}[0]"
        row.update({"clock": "clock", "reset": "reset"})
        for forward in range(3):
            row[f"io_forwardValid_{forward}"] = f"io_forwardMask_{forward}_0"
            row[f"io_forwardData_{forward}"] = f"io_forwardData_{forward}_0"
        for read in range(2):
            row[f"io_rdata_{read}_valid"] = f"read_{read}_valid"
            row[f"io_rdata_{read}_data"] = f"read_{read}_data"

        self.assertEqual(len(row), 32)
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


if __name__ == "__main__":
    unittest.main()
