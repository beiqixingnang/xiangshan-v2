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

GPT-6-Luna workers use max reasoning; the coordinator reviews and takes over
repeated failures. Full CPU replacement, Vortex verification/video upgrade and
controller integration remain subsequent milestones after V2 acceptance.

Check explicit implementation declarations before preparing tools or formal:

```powershell
py -B validation/v2_catalog_behavior_preflight.py --build Backend.Datapath.BypassPipeFamily
```

Declared `CONTRACT_ONLY` members block the Build and return exit code 1 without
exporting RTL or running formal. A declaration check never marks a Build ready
for formal; behavioral direct tests and the ABI/tool gates are still required.
The current Bypass/Pipe family has two such members. WbArbiter also needs its
registered direct test and two ABI repairs before a strict attempt.

Run a cheap, non-counting ABI/tool diagnostic for an implemented family:

```powershell
py -B validation/v2_catalog_family_strict_validator.py --build Cpu-Core-Backend.Datapath.VectorFamily-Hardware.py --preflight-only
```

The catalog runner reads exact identities from UHSC-Naming-Manifest.json,
requires the registered direct test before full formal, and stores reusable
checkpoints under ignored validation/.cache/strict-family. A missing direct
subject or ABI mismatch is a prerequisite failure, never a strict pass.

For focused Queue state repair, use the same strict gates on an explicit
member subset before retrying a full family:

```powershell
py -B validation/v2_queue_state_correspondence_validator.py --build Rocket.TLChildren.Family --member TLBuffer_2 --evidence v2-rocket-queue-state-focused-results.json
```

This diagnostic always records a zero Build-count delta and uses a separate
evidence filename. Complete member receipts use the same checkpoint directory;
reuse requires matching RTL, locked references, tools and producer hashes.
The negative-control rail also mutates outputs driven directly by child
instances; both DUT and reference mutations must fail the proof. Queue RAM
words preserve their `ram_ext.Memory` identity through memory mapping so
induction can establish state correspondence without assumptions or payload
masking. These proofs do not replace reset-entry or parent/system acceptance.

Large independent queue banks use complete driver-cone partitions before the
final unrestricted induction and whole-design `equiv_status -assert`. The
TLBuffer_27 proof now covers all 17,188 cells; the original single workset hit
the 900-second timeout, while the partitioned Yosys proof took about 34 seconds
and 332 MB. Both mutant sides use the same proof script. A missing partition
or any remaining unproven cell blocks success.

The Rocket TLChildren Build has a complete 11/11 strict receipt.
Its dedicated full-catalog producer is:

```powershell
py -B validation/v2_rocket_tlchildren_strict_validator.py
```

The producer uses the same full-cone partitions for queues and crossbar
arbiters, then asserts the entire design, checks every catalog member and
records two-sided negative controls. Its receipt binds the partition policy,
catalog resolver, common rail and registered direct test to current hashes.
Icache Prefetch now has a complete 7/7 strict receipt, bringing the audited
Build count to 46/118 at its integration milestone. Both pipelines implement their stage control, retries,
two-lane miss arbitration and data/exception paths. All 8,870 equivalence cells
prove, and both negative-control sides fail the mutated designs. Run:

```powershell
py -B validation/v2_catalog_family_strict_validator.py --build Frontend.Icache.Prefetch.Family
```

The full catalog rerun after normalizing the Build's five sections reused all
7/7 member proofs under the exact RTL/reference/tool/producer cache keys.
Acceptance remains pending for reset-entry, executable differential, parent
closure and system gates. TLXbar_8 preserves the full finite
manager address mask union, including the 0x31110000 hole found by SAT;
random route samples could not justify replacing that union with a complement.
See validation/v2-build-cpu-dependency-rocket-tlchildren-family-strict-evidence.json and
validation/v2-build-cpu-frontend-icache-prefetch-family-strict-evidence.json for current source hashes,
commands, lint, complete cell counts and two-sided controls.

FrontendBridge now has a complete strict receipt for its 91-port aggregate:
all 6,228 cells and both negative controls pass. Its twelve Queue(2) instances
retain the packed fields, `wrap`/`wrap_1` state, `nodeOut_a_q`/`nodeIn_d_q`
placement and `ram_ext.Memory` correspondence. Dequeue payloads remain in the
unrestricted proof even when valid is low. Six-channel FIFO scoreboards cover
450 deterministic random cycles and reset/backpressure cases.

The current audited Build count comes from the dynamic strict-progress JSON,
rather than these historical milestone examples. The FrontendBridge receipt
is validation/v2-build-cpu-memory-frontendbridge-strict-evidence.json; its
Scala source binding is declared in the auxiliary provenance map.

PMP has a current complete 5/5 family formal receipt with two-sided controls;
reset/startup and parent acceptance remain separate. EntryHandle corrects lock-bit positions,
zero-extension and WARL bit order, and preserves address-state identities for
induction through masked reads. Its 3,009 cells and both controls pass.
The direct suite now checks the locked ABI and actual behavior in about
0.4 seconds; the former module-name-only test exported all five designs and
took about 103 seconds. RTL export, determinism, ABI and formal remain required
in the strict rail. All five PMP members have executable implementations.
