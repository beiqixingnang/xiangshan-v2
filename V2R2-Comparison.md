# XiangShan Kunminghu V2 versus V2R2

There is no single current branch named exactly `kunminghu-v2r2`. The upstream
repository has several V2R2-labelled branches, and they represent different
hardware/release variants rather than a replacement for the maintained V2 line.
The comparison below is based on the official XiangShan repository and the
commits recorded in the local upstream metadata before it was vendored.

| line | observed tip | date | interpretation |
| --- | --- | --- | --- |
| `kunminghu-v2` | `d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af` | 2026-09-11 | actively maintained Kunminghu V2 baseline |
| `kunminghu-v2r2-s` | `f20670e6e719202fde29ad768dab1b2c0930e8c2` | 2026-08-12 | V2R2-S fork; one store-order fix after common ancestor `c4cfd2b78a755e7157e639559c24fb42d3aeebda` |
| `kunminghu-v2r2l` | `4f29a09516aa22dcf030f8dbd5dbe1cfd145ebc4` | 2026-08-31 | V2R2-L fork; relocatable physical-memory/address-map configuration plus NEMU/script updates |
| `kunminghu-v2r2-20250615` | `c8bbd5c6acf879d0df9dcc3974562b54187254db` | 2025-06-15 | historical V2R2 development line, not the current V2 baseline |
| `kunminghu-v2r2-930` | `c5bf01808890ebbf93fa9b415a0019d053be869c` | 2024-11-26 | older 930-era V2R2 line |

## Concrete hardware differences

The V2R2-L fork changes the memory/device map, not the core ISA contract:

- V2 default physical memory is `[0x80000000, 0x80000000000)`; V2R2-L uses
  `[0x80080000, 0x100000000)` and sets `SimMemSize` to `0x7ff80000`.
- Cached/executable PMA entries move from `0x80000000000`/`0x80000000` to
  `0x100000000`/`0x80080000`.
- The timer range moves from `0x38000000` to `0x60000`.
- UART16550 moves from `0x310b0000` to `0x20001000`.
- `system.SoC` derives the AXI memory window from configured `PmemRanges` and
  adds `PmemBase`; `top.YamlParser` accepts the V2R2-L memory/UART settings.
- The fork bumps the relocated NEMU reference and adds an emulator option alias.

The V2R2-S fork is much narrower. Relative to the V2 tip it has 25 changed
paths (16 Scala files), centered on store/vector replay and difftest behavior:
`MemBlock`, load/store queues and units, `Sbuffer`, vector split/merge bundles,
CSR trigger handling, and the AXI4 memory helper. Its tip is one commit beyond
the shared V2 ancestor, so it should be treated as a targeted fix fork rather
than a separate architecture.

The historical `kunminghu-v2r2-20250615` and `kunminghu-v2r2-930` branches are
far older. Against the current V2 tip they differ in hundreds of paths,
including top-level integration, CSR/device files, cache and backend plumbing,
tooling, and dependency revisions. Their generated RTL must not be mixed with
the current V2 reference.

## Baseline decision for this repository

The vendored source and `V2-Snapshot.json` intentionally use
`kunminghu-v2@d76ee7f...` as the behavioral baseline. If the target is a
V2R2-L chip, create a separately pinned source/config snapshot and regenerate
the complete reference SV; do not patch the V2 hash or silently substitute the
V2R2 address map. V2R2-S store fixes likewise require their own reference and
differential evidence.

For Python reuse, modules whose Scala semantics are unchanged can start from
the 35 candidates in `python/ported/`. SoC/address decode, AXI4Memory,
Parameters, timer/UART, cache-control ranges, and other map-sensitive modules
must remain parameterized or be rewritten against the selected V2/V2R2
reference. A prior V3 `ACCEPTED` or `BEHAVIOR_MATCHED` status is only a reuse
hint; it is not V2 acceptance evidence.
