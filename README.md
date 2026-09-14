# XiangShan Kunminghu V2 local snapshot

This repository vendors the complete pinned XiangShan Kunminghu V2 Scala and
dependency source tree under `upstream/`, carries 34 retained XiangShan-core
Python/Amaranth Build targets under `python/Program-System/System-Build/Build-Cpu/`
(one additional candidate is explicitly retired), and provides
a WSL SystemVerilog generator. The Python files are reuse candidates only;
V2-specific reference, direct-test, and differential evidence is still
required before acceptance.

See [V2-Snapshot.md](V2-Snapshot.md),
[V2R2-Comparison.md](V2R2-Comparison.md), and
[V2-Python-Rewrite-Strategy.md](V2-Python-Rewrite-Strategy.md), and
[`V2-Ported-Candidates.json`](V2-Ported-Candidates.json).

The exact old-to-final path transaction is recorded in
[`V2-Build-Relocation-Manifest.json`](V2-Build-Relocation-Manifest.json).

Phase 0 source classification, dependency/license inventory, contract audit,
and UHSC rename planning are authoritative in:

- [`V2-Phase0-Mapping-Manifest.json`](V2-Phase0-Mapping-Manifest.json)
- [`V2-Dependency-License-Inventory.json`](V2-Dependency-License-Inventory.json)
- [`V2-Ported-Contract-Audit.json`](V2-Ported-Contract-Audit.json)
- [`UHSC-Naming-Manifest.json`](UHSC-Naming-Manifest.json)
