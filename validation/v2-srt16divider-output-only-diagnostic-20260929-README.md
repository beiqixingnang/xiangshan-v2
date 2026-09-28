# SRT16DividerDataModule output-only diagnostic

This diagnostic asks whether the strict rail's 139 unproven internal
equivalence cells are only a matching limitation or whether the current Build
has a public-output behavior difference. The result is inconclusive: the
output-only sequential proof did not complete, and it produced no
counterexample. It therefore supports neither conclusion.

The run reused the current Build export and the locked SRT16DividerDataModule
reference through the shared strict rail and the conservation-audited section
5C multiline view. The Build hash was
`b7a5676f207c895ae4d7c152d04b87e24368560469e5717269f2fe0fb77d2900`; the
locked reference hash was
`71c183646518dd914a1569392ae993b5f20293579374178f573b1be4c8e15c7c`. The
reference view was trusted and included the locked CSA3_2_3956, CSA3_2_3960,
CSA3_2_3962, and RightShifter children. No Scala or locked SV was changed.

Two outer wrappers retained the exact 137-bit input ABI and all 66 public
output bits. The wrapper instances used distinct names, then Yosys compared
their outputs after flattening. Both proof runs created exactly 66 `$equiv`
cells, matching the declared output width; there were no internal equivalence
obligations in this wrapper-first comparison.

| Run | Time | Output cells proven | Output cells unproven | Result |
| --- | ---: | ---: | ---: | --- |
| Output-only, default induction depth 4 | 25.911 s | 1/66 | 65/66 | Unresolved, no counterexample |
| Output-only, induction depth 16 | 325.302 s | 1/66 | 65/66 | Unresolved, no counterexample |
| Reference-side mutation of io_in_ready | 25.929 s | 0/66 | 66/66 | Negative control detected |
| Build-side mutation of io_in_ready | 25.872 s | 0/66 | 66/66 | Negative control detected |

Both negative controls had an explicit unproven-equivalence failure marker,
retained the 66-output-cell guard, and had no tool or parse error. They confirm
that either wrapper side can affect the compared public outputs. The seq-16
retry remained within the 900-second per-run cap, used about 5.15 GiB sampled
peak Yosys RSS, and left roughly 17.3 GiB WSL memory available. All formal
commands ran serially, with no other formal process active.

An earlier runner launch returned 127 three times because the WSL image does
not contain `/usr/bin/time`. Yosys did not start during those attempts, so they
are recorded as an excluded launch failure, not as proof results. The rerun
used Linux `timeout` directly and sampled Yosys RSS through `ps`.

The default-depth proof and the depth-16 retry each left only io_in_ready
proven; io_out_valid and all 64 io_out_data bits remained unproven. Neither
run produced a counterexample or timed out. A true output difference is
therefore not demonstrated, and output equivalence is not established. The
diagnostic stops here as instructed; the strict Build evidence remains
STRICT_PENDING with 139 internal cells unproven. No ACCEPTED status or strict
progress change is claimed.

Machine-readable run details, input hashes, return codes, resource samples,
and output-log hashes are in
`v2-srt16divider-output-only-diagnostic-20260929.json`. Full formal logs are
retained outside the repository under
`C:/Temp/uhsc_srt16divider_output_only_20260928T220130Z`.
