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


## Verification workflow and local paths

Formal Build files use their Cpu-Core/Cpu-Memory parent prefix; direct tests
use Testing-Cpu-. The path transaction and immutable proof origins are recorded
in UHSC-Naming-Manifest.json. Local processor APIs use UHSCore, UHSTile and
UHSCTop; locked source/reference identities stay unchanged in evidence.

The shared family rail runs static gates and lint before serialized formal,
retains member checkpoints, and reuses only complete PASS receipts with matching
proof inputs, tool/runtime versions and producer dependencies. Historical
producer snapshots are inert text under validation/validation-Proof.Producer;
product code never loads them. The independent progress audit checks current
DUTs, locked references, original receipt integrity and snapshot hashes.

GPT-6-Luna workers use xhigh reasoning; the coordinator reviews and takes over
repeated failures. Full CPU replacement, Vortex verification/video upgrade and
controller integration remain subsequent milestones after V2 acceptance.

Run a cheap, non-counting diagnostic before sending a family to formal:

```powershell
py -B validation/v2_catalog_family_strict_validator.py --build Cpu-Core-Backend.Datapath.VectorFamily-Hardware.py --preflight-only
```

The catalog runner reads exact identities from UHSC-Naming-Manifest.json,
requires the registered direct test before full formal, and stores reusable
checkpoints under ignored validation/.cache/strict-family. A missing direct
subject or ABI mismatch is a prerequisite failure, never a strict pass.
