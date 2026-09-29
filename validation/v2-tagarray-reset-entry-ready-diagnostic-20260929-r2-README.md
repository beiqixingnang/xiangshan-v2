# TagArray reset-entry ready diagnostic — 2026-09-29 r2

This is a follow-up to `v2-tagarray-public-partition-diagnostic-20260929`. The earlier record remains unchanged. This run changed only the diagnostic wrapper: the DUT and reference reset-entry helpers use side-specific names (`_dut_i_*` and `_ref_i_*`), so helper state cannot become an accidental equivalence point.

The proof retains all 41 public input ports and all 313 input bits. It compares one public output, `io_read_ready` (one bit). The wrapper drives reset high through the first rising edge for each instance, then reconnects reset to the same external reset input. The source audit independently confirms both sides use a 9-bit counter initialized to zero, saturating at bit 8, with the same `+1` transition before saturation and the same public ready equation. No counter equality is assumed or injected.

## Result

The serial baseline completed without a timeout and returned exit code 1. Yosys reduced the miter to exactly one `$equiv` cell in its statistics, corresponding to the single public ready obligation. That cell remained unproven through induction steps 1–4; there was no success marker and no counterexample. The reset-entry contract therefore did not close the proof.

Because the baseline failed, the target and reference mutations were deliberately not run. Their status is `NOT_RUN_BASELINE_FAILED`; no current-digest negative control is claimed. The bank0 and bank1 partitions remain `NOT_RUN_PENDING_FOLLOWUP`.

The machine record is [v2-tagarray-reset-entry-ready-diagnostic-20260929-r2.json](v2-tagarray-reset-entry-ready-diagnostic-20260929-r2.json). The runner is [v2_tagarray_public_partition_diagnostic.py](v2_tagarray_public_partition_diagnostic.py). The diagnostic remains `STRICT_PENDING` and does not update canonical strict evidence or progress.

## Frozen inputs

Build SHA-256: `0978d5e6bbe131c3379897690555af141eba6010c859e61dd51386553d51e697`.

Locked `TagArray.sv` SHA-256: `24d984641c94512391a2b3b405a8554d580f91ca6355e774e03f3bdcc9eb4faa`.

The 5C multiline reference view passed all seven conservation and register-equation audits. Locked sources, the Build, and the main repository were not modified.
