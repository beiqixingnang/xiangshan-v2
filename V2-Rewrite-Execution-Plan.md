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

The final product placement is deliberately separate from migration tooling.
Build files are staged at their final `python/Program-System/System-Build/`
paths in this auxiliary repository. Migration-only reference extractors,
differential harnesses, tool logs, caches, generated SV/VCD, and evidence JSON+remain under `.agents/xiangshan-v2/validation/`. Only after all applicable+family/parent/milestone gates reach `ACCEPTED` may reusable direct tests be+adapted into the main repository's `Program-System/System-Testing/Testing-Cpu/`
and registered in its Testing Manifest. The auxiliary repository remains the+traceable source of the full locked-reference evidence package; no Build file+may import it.

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
