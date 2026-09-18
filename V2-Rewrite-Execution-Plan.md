# Kunminghu V2 rewrite and localization execution plan

## Objective

Rewrite the usable XiangShan Kunminghu V2 hardware closure in Python/Amaranth,
validate each completed batch against the pinned V2 Scala-generated reference,
and localize project-owned external identities to UHSC. The plan deliberately
does not require a one-to-one Scala/Python mapping for external dependencies.

## Fixed baseline

- V2 source: `upstream/` at
  `d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af`.
- Reference artifact: `XSTop.sv`, SHA-256
  `8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d`,
  228590583 bytes.
- Existing V3-derived candidates: 35 manifest entries, of which 34 retained
  files are under `python/Program-System/System-Build/Build-Cpu/` and one is
  explicitly retired; retained files remain `CANDIDATE_V2_REUSE` until
  revalidated.
- Source and reference are immutable inputs. V2R2-S and V2R2-L are separate
  baselines and must not be mixed into this plan.

## Phase 0 — manifests and naming freeze

Create a V2 mapping manifest with one entry per V2 behavioral closure, not one
entry per dependency source file. Core XiangShan entries must use the final
staging path under `python/Program-System/System-Build/` and a
`Build-<hardware ID>-Hardware.py` basename so a verified file can be copied
to the main repository without a second rewrite. Each entry contains `family_id`,
`closure_root`, `source_paths`, `target_paths`, `source_commit`,
`covered_children`, `parameters`, `observation_points`, `v2_status`,
`direct_test`, `reference_evidence`, `differential_evidence`, and
`localization_map`. Build a source inventory and dependency DAG, classify
source files as core, hardware dependency, test/workload, generated support,
or non-target metadata, and freeze the UHSC rename map. The first Phase 0
deliverable also compares all 35 carried V3 candidates with V2 and records
exact `REUSED`, `REWRITTEN`, `RETIRED`, `SPLIT`, or `RELOCATED` outcomes; no
candidate is copied into a V2 closure solely because its old path still exists.

## Phase 1 — XiangShan core closures

Process in dependency order, with each batch implemented, tested, reviewed,
and committed before the next batch:

1. Decode/ISA and arithmetic leaves (`RiscvInst`, `Instructions`, CSR tables,
   shift/CSA/crypto helpers, FLI, divider utilities).
2. Frontend/BPU and I-cache control leaves (replacement state, saturating
   counters, RVC expansion, ICache utility/M.S.H.R and replacer).
3. Backend datapath/FU families and vector utility leaves.
4. Memory/cache leaves (AMOALU, tag/replacer, queue and forwarding helpers).
5. Core integration closures (`Backend`, `Frontend`, `MemBlock`, `L2Top`,
   `XSTile`, and top-level adapters) only after child evidence is complete.

The 35 existing candidates seed batches 1–4. V2 Scala diffs decide whether a
candidate is reused, forked and rewritten, or retired/split.

## Phase 2 — external dependency families

Implement only hardware-bearing closures reachable from the selected V2 core:

- `utility` and small Rocket protocol leaves: parameterized utility families.
- `rocket-chip` clock/reset, queues, arbiters, diplomacy and bus bridges:
  family closures with explicit protocol contracts.
- `fudian` and `yunsuan`: scalar/vector floating-point and integer families,
  keeping pipeline and latency boundaries.
- `huancun`, `coupledL2`, and `openLLC/openNCB`: cache slice, directory,
  MSHR, bridge, SRAM and replacement families; do not flatten the hierarchy.
- `ChiselAIA`, `ChiselIOPMP`, and difftest: interface contracts first, then
  only the hardware leaf closures needed by the chosen top.
- `ready-to-run`: workload/test input only, not a hardware rewrite target.

Each family is validated by a parent closure test plus child coverage entries;
unreachable or test-only files remain source references and are not copied as
fake hardware modules.

## Phase 3 — UHSC integration and external naming

Build the localized Python top and generated wrapper with external identity
`UHSCTop`. Keep all V2 reference names in provenance metadata. Validate the
wrapper's ports and hierarchy against the V2 top, then run CPU/cache/memory
transaction tests. Only project-owned external names are changed; internal
protocol names stay stable.

## Phase 4 — verification execution after family rewrite

The rewrite inventory is structurally complete only when the locked 1976-module
catalog is covered by source-backed family subjects. Verification then proceeds
in dependency order and records a separate bounded result for each gate:

1. Re-run the shared Build audit (UTF-8/LF, AST, compile, exact import,
   deterministic adapter, and single-file Pyright) after every implementation
   batch. A transient tool-output change is not behavioral evidence.
2. For each family, run its direct reset/steady-state/boundary tests and the
   required Verilator/Yosys checks. Keep the result `*_BOUNDED` until its parent
   closure is proven; leaf success never implies top-level equivalence.
3. Bind XSCore's Frontend, Backend, and MemBlock envelopes through an explicit
   308-port bridge, then run the XSCore parent validator. Bind L2Top's exact
   TL2TL, Xbar, Buffer, merger, and error-unit instances through its 441-port
   bridge, then run the L2Top parent validator. Missing or pending children
   keep `closure_complete=0`.
4. Bind XSTile to the XSCore/L2Top adapters and all three locked IntBuffer
   variants, then run the XSTile closure validator. IntBuffer direct evidence
   is not a substitute for XSTile closure.
5. Validate XSTop-to-UHSCTop localization and all 204 external ports, capture
   lower-case `imsic_bus_top`, and run the complete hierarchy/structural
   differential probe. The reduced top probe remains reduced until every root
   child has source-backed behavior evidence.
6. Run license review, reproducibility/determinism checks, and the final locked
   reference differential. Only after all gates pass and the user approves may
   evidence be promoted to `ACCEPTED` and copied to the main repository.

Authoritative progress counters are the locked-module coverage manifest, the
current Build line count, the shared-audit pass count, and the top-closure task
list. Evidence JSON must retain failures and pending gates rather than rewriting
them as success.

## Batch size and delegation

- A normal leaf batch contains 30–40 closely related modules when their
  equations and source provenance are homogeneous; a stateful family contains
  at most 5 closure roots and an explicit child list. Smaller batches are used
  only when a family boundary or reference module genuinely prevents safe
  aggregation.
- A worker owns one disjoint family and may edit its Python targets, direct
  harness, evidence JSON, and mapping fragment only.
- The coordinator owns manifests, naming policy, top-level adapters, plan
  events, conflict resolution, and pushes.
- Workers use Terra for all implementation batches. The coordinator may set
  `max` (or `xhigh` when a shorter bounded pass is sufficient) for file-writing
  and repair work so that each aggregate Build is completed in one focused
  transaction; `high` remains acceptable only for mechanical leaf batches.
  Parent and milestone closures should use `max` by default.
  They must return a commit hash, changed paths, evidence paths, exact
  commands, and unclosed gates.
- Existing carried candidates may contain V3-era contract debt (missing
  bilingual function comments, leading-underscore helpers, compatibility
  aliases, or imports outside the allowed band). Workers must repair that debt
  before treating a candidate as a V2 target; they must not silently inherit
  those violations.
- No worker may modify the locked V2 source, the main hardware product tree,
  or another worker's family.

### Throughput policy

Workers run the static contract, direct tests, and the reference check required
by the batch tier in one commit. Leaf batches do not start a fresh full-top
Verilator/Yosys build. Family and parent batches use the content-addressed
cache under `validation/.cache/<sha256>/`; a matching target/configuration/tool
key reuses the prior result. The complete top probe and full hierarchy
differential run only at milestone events or after an invalidating parent
change.

The implementation worker and focused validator may overlap on non-dependent
batches. The validator spot-checks one batch per five completed batches and
escalates only failures or high-risk parent/protocol changes to a full rerun.
The coordinator records both `STRUCTURE_VERIFIED` and
`BEHAVIOR_VERIFIED_<family>` while keeping `ACCEPTED` locked.

### Bulk landing mode

When the user requests large-scale landing, implementation workers may first
land all disjoint aggregate Build files for a family in one transaction. The
coordinator then runs one shared static sweep over the whole landed set (AST,
`py_compile`, import, Pyright and adapter export) instead of re-running the
same setup per file. Direct/reference/Verilator/Yosys checks are batched by
family after landing. A family remains `STRUCTURE_PENDING` if any file fails;
no individual smoke PASS is promoted to behavior or `ACCEPTED`. This mode is
the default for the remaining REWRITE_FREEZE work to maximize throughput.

## Rewrite-freeze phase

The execution order is now explicitly split into two large phases:

1. `REWRITE_FREEZE`: complete the frozen set of 78 aggregate Build subjects
   (46 core leaves, 8 core parents, 23 dependency-family subjects, and one
   UHSC integration subject; one source entry is retired/excluded). A worker
   may own a disjoint family batch and write several Build files before any
   expensive reference differential is started.
2. `BATCH_VALIDATION`: after the Build set is frozen, run family and parent
   differential closures in dependency order, followed by the milestone
   complete-top gate.

Every Build file must pass the rewrite-freeze basic gate before it is counted
as `STRUCTURE_VERIFIED`: UTF-8/LF and five-zone audit, AST parse,
`py_compile`, exact-path import, Pyright on the owned batch, and deterministic
same-name `build_verilog()` export with syntax-valid generated Verilog. A
basic-gate pass is not a behavior pass. The worker records the basic result and
mapping with the implementation batch; it does not run a fresh full-top
Verilator/Yosys compile for every leaf.

The Pyright check is strict: file-level directives that disable diagnostic
classes are not accepted as a freeze result. Dynamic Amaranth boundaries must
be repaired with narrow, documented typing or protocol annotations, and any
non-zero diagnostic count keeps the target outside `STRUCTURE_VERIFIED`.

The final product placement is deliberately separate from migration tooling.
Build files are staged at their final `python/Program-System/System-Build/`
paths in this auxiliary repository. Migration-only reference extractors,
differential harnesses, tool logs, caches, generated SV/VCD, and evidence JSON
remain under `.agents/xiangshan-v2/validation/`. Reusable one-to-one direct
tests may be maintained in the auxiliary
`python/Program-System/System-Testing/Testing-Cpu/` tree while a family is
being developed; they must not be counted as reference evidence or imported
by Build files. Only after all applicable family/parent/milestone gates reach
`ACCEPTED` may those tests be adapted into the main repository's
`Program-System/System-Testing/Testing-Cpu/` and registered in its Testing
Manifest. The auxiliary repository remains the traceable source of the full
locked-reference evidence package.

## Acceptance gates

The evidence graph has two parallel rails. The structure rail is
`PYTHON_PRESENT` → `STRUCTURE_VERIFIED`; the behavior rail is
`DIRECT_TEST_PASS_BOUNDED` → `V2_REFERENCE_MATCHED` →
`BEHAVIOR_VERIFIED_<family>` → `PARENT_CLOSURE_MATCHED`. UHSC localization and
license evidence attach to both rails. The final release gate remains
`ACCEPTED` only after complete closure and user approval.

Each transition requires machine-readable evidence. `DIRECT_TEST_PASS_BOUNDED`
never implies reference equivalence; `V2_REFERENCE_MATCHED` never implies
parent integration; `STRUCTURE_VERIFIED` never implies behavioral equivalence;
and no intermediate rail implies license or release acceptance. Blocked or
missing-reference closures remain explicitly blocked.

## Delivery order

1. Commit this ruleset and plan, then update the append-only hardware plan
   with the V2 baseline correction.
2. Start Phase 0 inventory and naming manifest.
3. Delegate Phase 1 batches; each worker completes rewrite + verification +
   final Build-path relocation in one transaction, then the coordinator
   reviews and pushes. No validated core target may remain only under
   `python/Program-System/System-Build/Build-Cpu/`.
4. Expand to Phase 2 dependency families after core closure evidence exists.
5. Run Phase 3 integration and present a merge-ready preview branch for user
   approval. Existing future plans (OpenC910 replacement, Vortex validation,
   graphics completion, and other RISC-V64 controller work) remain unchanged.

## Phase 0 freeze addendum — scan before implementation

Implementation does not begin until these read-only inventories are committed
and reviewed:

1. `V2-Core-Rewrite-Inventory.json` — every reachable V2 XiangShan hardware
   closure, final `Build-*-Hardware.py` path, source Scala paths, closure root,
   children, parameters, observation points, and status.
2. `V2-Dependency-Family-Inventory.json` — every reachable external hardware
   dependency family, covered Scala children, proposed aggregate Build file,
   protocol boundary, and exclusion rationale for test-only or unreachable
   files.
3. `V2-Rewrite-Batch-Plan.json` — disjoint implementation batches, owner,
   dependency order, expected file count, and the single validator assigned to
   each batch.

These inventories are authoritative for the rewrite count. A child Scala file
covered by an aggregate family is not counted as an additional Python file.
Counts must distinguish `core_files`, `dependency_family_files`,
`retired_or_excluded`, and `total_planned_build_files`.

## One-transaction worker contract

Each implementation worker receives one disjoint batch and performs, in one
transaction and one commit: V2 implementation at the final Build path, UHSC
project-facing naming, the direct/reference checks required by its tier, static
audits, and machine-readable evidence/mapping updates. Verilator/Yosys are
mandatory for family/parent/milestone tiers and may be reused from the
content-addressed cache; they are not a fresh requirement for every leaf.
Workers may not leave targets under `python/ported`, borrow another family,
modify `upstream/` or the main repository, or mark `ACCEPTED`.

## Independent validator contract

Implementation workers may continue on non-dependent batches while a focused
validator spot-checks one batch per five completed batches. The validator checks
changed paths and source/reference hashes, reruns the tier-required focused
gates, and records `VALIDATOR_PASS` or an explicit failure. A failure or a
high-risk parent/protocol change escalates that batch and adjacent dependents to
serial full validation. Only the coordinator pushes the batch and updates the
main preview plan. Bounded passes remain bounded until parent, license, UHSC
wrapper, and user-approval gates close.

## Full Kunminghu V2 generation gate

Reduced family and parent passes are intermediate evidence only. Before this
goal can be completed, the auxiliary repository must emit a complete
Python/Amaranth-generated Kunminghu V2 top hierarchy from the frozen closure:
all selected core parents, selected dependency families, and the UHSC top
adapter must elaborate into one reproducible SystemVerilog artifact. The final
gate must compare the generated hierarchy/module and port inventory against
the locked V2 XSTop snapshot, run Verilator/Yosys on the complete artifact,
and record any intentionally omitted conditional or inlined source with an
explicit rationale. A reduced parent wrapper, a set of independent family
files, or a successful syntax-only smoke test does not satisfy this gate.

## Throughput wave amendment (2026-09-16)

The rewrite phase is implementation-first and proceeds in waves. A wave must
land a complete aggregate family or parent closure before its evidence is
refreshed; evidence-only or hash-only commits do not count as rewrite
progress. Each worker owns a disjoint batch of at least three dependency
families or one complete core parent (roughly 30--40 covered Scala modules,
where the closure permits) and may reuse already landed leaf modules.

At most one focused protocol harness repair may run alongside two implementation
workers. When a worker reports its commit, the coordinator records its file,
line, family, and Scala-path deltas immediately and releases the slot for the
next wave. Leaf workers run static checks and direct Amaranth tests; Verilator
and Yosys are reserved for family/parent checkpoints or a failed spot-check.
This keeps the implementation lane moving while preserving the existing
evidence and acceptance gates.

## Hierarchy-completion wave amendment (2026-09-16)

The rewrite-freeze count of 78 aggregate Build subjects is a *closure-subject*
bound, not a statement that the locked hierarchy is implemented.  A read-only
scan of the pinned artifact (`validation/v2-locked-hierarchy.json`, 1976 modules
with exact ANSI ports, child instances, and Scala provenance) joined with the two
rewrite inventories (`validation/v2-hierarchy-coverage.json`) shows:

- 156 locked modules are reached by a bounded core subject,
- 722 locked modules are reached by a dependency-family subject,
- 1098 locked modules have **no** subject at all.

The uncovered set is concentrated: the `xiangshan/backend/fu/NewCSR` family alone
accounts for roughly 600 modules, and the Chisel `Decoupled`/`Arbiter` primitives
account for a further 240.  A second wave is therefore authorised to add new
aggregate Build subjects that implement these families:

| new Build subject | covered family | representative locked modules |
| --- | --- | --- |
| `Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.CSRModule-Hardware.py` | `CSRModule` register family | 364 |
| `Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.CSRLite-Hardware.py` | CSR level/map modules (`MachineLevel`, `Unprivileged`, `HypervisorLevel`, `DebugLevel`, `CSRPMP`, `CSRPMA`, `CSRAIA`) | ~230 |
| `Cpu-Core/Build-Cpu.Dependency.Chisel.Decoupled-Hardware.py` | Chisel `Queue1_*`/`Queue2_*`/`Queue68_*` | ~208 |
| `Cpu-Core/Build-Cpu.Dependency.Chisel.Arbiter-Hardware.py` | Chisel `Arbiter*`, `AsyncQueue*`, `Repeater`, `ValidIOBroadcast` | ~70 |

Wave 1 landed all four subjects and moved locked-module coverage from
156 core + 722 family + 1098 missing to **521 core + 973 family + 482 missing**
(commit `8b181bc`).  A second wave is authorised for the largest remaining
clusters:

| wave-2 Build subject | covered family | representative locked modules |
| --- | --- | --- |
| `Cpu-Core/Build-Cpu.Backend.Issue.Entries-Hardware.py` | issue/rename entries, busy tables, wakeup queues | `OthersEntry*`, `EnqEntry`, `Entries`, `IssueQueue`, `FuBusyTableWrite`, `BusyTable`, `MultiWakeupQueue` |
| `Cpu-Core/Build-Cpu.Backend.Exu.FuncUnit-Hardware.py` | execution-unit and functional-unit leaves | `FuncUnit`, `ExeUnit`, `Bku`, `Dispatcher` |
| `Cpu-Core/Build-Cpu.Backend.Regfile.Regfile-Hardware.py` | register file, rename snapshot, writeback arbitration | `Regfile`, `SnapshotGenerator`, `FreeList`, `RenameTable`, `RFReadArbiter`, `RealWBArbiter`, `RFWBConflictChecker` |
| `Cpu-Memory/Build-Cpu.Memory.Lsqueue.Uncache-Hardware.py` | uncache load-queue entries, TLB storage, vector split leaves | `UncacheEntry*`, `LoadQueueUncache`, `TLBStorage`, `VSplit*`, `indexedLSUopTable` |

Rules for this wave, in addition to the existing contract:

- A new Build subject must justify its path by a Scala source root and must list
  every covered locked module in its evidence file.
- Coverage is counted by *implemented module*, not by file.  Landing four files
  does not reduce rewrite debt unless the modules inside them are source-backed
  and their ports are checked against `validation/v2-locked-hierarchy.json`.
- A module whose behaviour is transcribed from the pinned artifact records
  `DIRECT_TEST_PASS_BOUNDED` at most; `BEHAVIOR_MATCHED`, `INTEGRATED`, and
  `ACCEPTED` remain locked.
- The coordinator records the new subjects in `V2-Rewrite-Freeze-Manifest.json`
  and re-runs the shared static sweep, Pyright, and the generation probe after
  the wave lands.

## Rewrite-debt checkpoint (2026-09-16)

The shared freeze audit is a static scaffold gate, not proof that every
candidate has been semantically rewritten.  The authoritative core inventory
still contains 34 entries with `v2_status = CANDIDATE_V2_REUSE`; those files
must receive source-backed V2 logic before they can be counted as landed
rewrites.  A wave therefore counts only when it changes at least three
disjoint aggregate Build files (or one complete parent), records the covered
Scala-path delta, and passes one shared static sweep.  Evidence-only, hash-only,
or protocol-log-only commits do not reduce this rewrite debt.  Until the debt
is closed, reports must show both the 78/78 static freeze result and the
remaining candidate count separately.

## Dynamic Build and throughput amendment (2026-09-17)

The original 78 aggregate subjects are retained as a historical planning
baseline, not as a maximum or completion criterion. The effective completion
scope is the full pinned Kunminghu V2 hierarchy: every one of the 1976 locked
modules must be covered by a source-backed core or dependency family subject,
with parent and top-level closure evidence still required. Build-file count is
derived telemetry and may increase when a real source/protocol/clock/reset
boundary requires a new aggregate subject.

An aggregate Build may cover multiple Scala files and parameterized child
instances. A new Build is justified only when its boundary, covered modules,
and observation points are distinct and recorded in the inventories. Splitting
solely to increase file count is prohibited; reverting to one Scala file per
Python file is explicitly out of scope.

Each normal implementation round must add at least 5000 effective Python
implementation lines across formal Build files. Effective lines exclude blank
lines, comment-only lines, validators, evidence JSON, logs, generated RTL,
temporary scripts, and formatting-only changes. The coordinator records both
raw Build lines and effective lines; emergency correctness fixes below the
threshold are recorded as exception fixes and do not substitute for a normal
throughput round.

Every round report must include: covered locked modules / 1976, structure-
verified modules, behavior-verified modules, missing modules, current Build
count, current raw/effective Build Python lines, this-round effective additions,
new Scala source roots, validation results, and the commit pushed. Coverage is
never promoted to behavioral equivalence merely because a Build file exists.
