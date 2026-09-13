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
- Existing V3-derived candidates: 35 files under `python/ported/`; all are
  `CANDIDATE_V2_REUSE` until revalidated.
- Source and reference are immutable inputs. V2R2-S and V2R2-L are separate
  baselines and must not be mixed into this plan.

## Phase 0 — manifests and naming freeze

Create a V2 mapping manifest with one entry per V2 behavioral closure, not one
entry per dependency source file. Each entry contains `family_id`,
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

- A normal leaf batch contains 8–20 closely related modules; a stateful family
  contains at most 5 closure roots and an explicit child list.
- A worker owns one disjoint family and may edit its Python targets, direct
  harness, evidence JSON, and mapping fragment only.
- The coordinator owns manifests, naming policy, top-level adapters, plan
  events, conflict resolution, and pushes.
- Workers use Terra with maximum reasoning. They must return a commit hash,
  changed paths, evidence paths, exact commands, and unclosed gates.
- Existing carried candidates may contain V3-era contract debt (missing
  bilingual function comments, leading-underscore helpers, compatibility
  aliases, or imports outside the allowed band). Workers must repair that debt
  before treating a candidate as a V2 target; they must not silently inherit
  those violations.
- No worker may modify the locked V2 source, the main hardware product tree,
  or another worker's family.

## Acceptance gates

`PYTHON_PRESENT` → `DIRECT_TEST_PASS_BOUNDED` → `V2_REFERENCE_MATCHED` →
`UHSC_LOCALIZED` → `PARENT_CLOSURE_MATCHED` → `ACCEPTED`.

Each transition requires machine-readable evidence. `DIRECT_TEST_PASS_BOUNDED`
never implies reference equivalence; `V2_REFERENCE_MATCHED` never implies
parent integration; `UHSC_LOCALIZED` never implies license or release
acceptance. Blocked or missing-reference closures remain explicitly blocked.

## Delivery order

1. Commit this ruleset and plan, then update the append-only hardware plan
   with the V2 baseline correction.
2. Start Phase 0 inventory and naming manifest.
3. Delegate Phase 1 batches; each worker completes rewrite + verification +
   localization together, then the coordinator reviews and pushes.
4. Expand to Phase 2 dependency families after core closure evidence exists.
5. Run Phase 3 integration and present a merge-ready preview branch for user
   approval. Existing future plans (OpenC910 replacement, Vortex validation,
   graphics completion, and other RISC-V64 controller work) remain unchanged.
