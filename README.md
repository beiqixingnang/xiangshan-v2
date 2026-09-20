# XiangShan Kunminghu V2 local snapshot

This repository vendors the complete pinned XiangShan Kunminghu V2 Scala and
dependency source tree under `upstream/`, carries the aggregated
Python/Amaranth Build targets under `python/Program-System/System-Build/Build-Cpu/`,
and provides a WSL SystemVerilog generator. File presence and module mapping do
not imply behavior equivalence; the authoritative strict numerator and dynamic
Build denominator are rebuilt by `validation/v2_strict_equivalence_progress.py`.
Parent closure, complete XSTop differential, license review, and user approval
remain separate acceptance gates.

Generate the locked V2 SystemVerilog without network access, then reproduce or
verify the ignored per-module reference directory with:

```bash
OFFLINE=1 scripts/generate-v2-systemverilog.sh
python3 scripts/rebuild-v2-reference-sv.py \
  --xstop /home/lishuo/xs-v2-local/build/rtl/XSTop.sv
python3 scripts/rebuild-v2-reference-sv.py \
  --xstop /home/lishuo/xs-v2-local/build/rtl/XSTop.sv --verify-only
```

The rebuild refuses an XSTop hash other than the pinned Kunminghu V2 artifact
and requires all 1976 hierarchy slices to match the tracked inventory.

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
