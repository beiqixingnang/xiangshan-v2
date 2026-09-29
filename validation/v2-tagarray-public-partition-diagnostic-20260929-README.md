# TagArray public-output partition diagnostic — 2026-09-29

## Scope and status

This diagnostic preserves the complete 313-bit TagArray input surface and divides the 345 public output bits into three disjoint obligations:

| Partition | Public outputs | Bits | Run status |
| --- | --- | ---: | --- |
| ready | `io_read_ready` | 1 | Ran; not proven |
| bank0 | `io_resp_0`, `io_resp_1`, `boreChildrenBd_bore_rdata` | 172 | `NOT_RUN_PENDING_FOLLOWUP` |
| bank1 | `io_resp_2`, `io_resp_3`, `boreChildrenBd_bore_1_rdata` | 172 | `NOT_RUN_PENDING_FOLLOWUP` |

The partition map covers every public output exactly once. Each ready wrapper retains all 41 input ports, with their original 313 bits. The locked reference closure was passed through the trusted section 5C view; all seven top/child audits preserved line counts and sequential update equations.

The machine record is [v2-tagarray-public-partition-diagnostic-20260929.json](v2-tagarray-public-partition-diagnostic-20260929.json). The runner is [v2_tagarray_public_partition_diagnostic.py](v2_tagarray_public_partition_diagnostic.py). The diagnostic status remains `STRICT_PENDING`; this is not a full TagArray proof or an acceptance result.

## Ready result

Three serial Yosys runs completed under a 900-second per-run cap, using `C:/Temp/uhsc_tagarray_ready_diag_fk154ig1`. None timed out.

- The baseline returned 1 with one public `io_read_ready` `$equiv` cell unproven. Induction failed at steps 1–4; there was no success marker or counterexample. The log reports 18 initially unconstrained register values, consistent with two independently represented 9-bit reset counters lacking an established state relation in this wrapper-only run.
- Inverting the DUT wrapper's `io_read_ready` assignment also left one equivalence cell unproven.
- Inverting the reference wrapper's `io_read_ready` assignment did the same.

The two mutations were applied on their intended sides, but both mutated runs fail in the same way as the unmutated baseline. Therefore they are **inconclusive**, not decisive negative controls; the current-digest two-sided negative-control gate remains open. No internal state matching was enabled or claimed.

## Resource observation

The selective-port Amaranth export remains about 6.8 MB and 277,000 lines, nearly the same size as the full export. After the public ready wrappers were flattened and optimized, Yosys reduced the miter to roughly 28–29 cells with one `$equiv` obligation and two `$sdff` counters. The first partition therefore isolated the reset-counter proof obligation but did not establish how to relate its initially unconstrained states.

The next proof step needs an explicit, justified relation for the two 9-bit reset counters (or an approved reset-entry model) while keeping the wrapper's only obligation on the public ready output. This diagnostic does not run that follow-up or either bank partition.

## Frozen sources

Build, strict rail, 5C helper, locked TagArray, and six locked child hashes are recorded in the JSON. The Build and locked reference/children were not modified. No canonical strict evidence or progress file was changed.
