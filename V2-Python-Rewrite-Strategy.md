# V2 Python/Amaranth rewrite strategy

## What was moved

`python/ported/` contains 35 XiangShan-core candidates selected from the V3
backlog. The selection is limited to `scala/src/main/scala/xiangshan/**` and
requires the previous V3 status to be `ACCEPTED` or `BEHAVIOR_MATCHED`. The
machine-readable mapping is in `V2-Ported-Candidates.json`.

Those statuses are provenance only. They were established against the V3
reference commit (`0ff31c2...`), not this V2 snapshot. Every candidate remains
`CANDIDATE_V2_REUSE` until its V2 source mapping, direct test, reference SV,
and differential evidence are complete.

## Reuse versus rewrite decision

Use the V2 Scala tree as the sole behavioral authority. For each candidate,
compare the V3 source path and implementation with the corresponding V2 path:

1. If the V2 file is present and its observable interface/state logic is
   unchanged, reuse the Python implementation as a starting point and rerun
   all V2 tests.
2. If ports, reset/clock behavior, parameters, timing, or state transitions
   changed, fork the Python file and rewrite it from the V2 source. Keep the
   old implementation only as a named V3 reference, never as an implicit
   dependency.
3. If the V2 file was removed or split, record the mapping as retired/split
   and create a new family entry rather than forcing a one-to-one filename
   match.

The previous V3 result can reduce typing, but it cannot satisfy a V2 evidence
gate. In particular, V2/V2R2 address-map and memory-helper changes require new
tests even when the module name is identical.

## External dependency policy

Do not copy the V3 dependency rewrites wholesale. The vendored V2 tree is the
baseline, and dependencies should be condensed by hardware closure:

- `utility`, selected `rocket-chip` leaves, and small protocol helpers can be
  consolidated into parameterized utility families when their ports and
  combinational/sequential semantics match.
- `difftest`, `ChiselAIA`, and `ChiselIOPMP` should first be represented by
  interface contracts; only the hardware-bearing leaves needed by a selected
  closure need Python implementations.
- `coupledL2`, `huancun`, `openLLC/openNCB`, `fudian`, and `yunsuan` are
  stateful/high-fanout closures. Keep family boundaries (cache slice, bridge,
  floating-point/vector unit, SRAM/queue) and parameterize them; do not flatten
  thousands of Scala files into one opaque Python file.
- `ready-to-run` is a workload/test dependency, not a hardware rewrite target.

Each family should record `family_id`, `closure_root`, V2 source paths,
interface contract, parameters, covered child paths, and evidence hashes. A
parent closure test may cover children, but only when the coverage manifest
lists the exact child instances and observation points.

## Execution order

1. Freeze V2 source/dependency hashes and generate the V2 reference SV.
2. Diff the 35 candidates against V2 and classify exact/rewrite/retired.
3. Port exact matches first, then the smallest changed leaves (decode,
   arithmetic, queue/replacer utilities).
4. Build closure-level tests for frontend/backend/cache families; avoid a
   separate expensive top-level compile for every leaf.
5. Require V2 direct test, static checks, reference comparison, and a traceable
   commit before promoting any module to `ACCEPTED`.

This keeps the useful V3 work while preventing V3-specific behavior or
dependency revisions from being mistaken for V2 equivalence.
