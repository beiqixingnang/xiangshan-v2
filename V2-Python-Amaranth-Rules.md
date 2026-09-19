# Kunminghu V2 Python/Amaranth rewrite rules

This file is the execution contract for the V2 rewrite. It is subordinate to
the repository's `Program-Document/Document-Spec/Hardware-System-Specification.md`.
The vendored V2 Scala tree and its generated SystemVerilog are the only
behavioral authority. Existing V3 Python is reusable source material, never a
V2 acceptance oracle.

For strict Build counting, the concrete behavior boundary is the module and
port surface emitted in the locked DefaultConfig `XSTop`. Chisel/FIRRTL may
remove generic Scala parameters or IO fields after constant propagation and
dead-code elimination. A proof over such a module must say
`locked_xstop_specialization`, list every omitted Scala field and constant
specialization, and explicitly set `scala_class_claimed` to false. It proves
the locked processor instance only; it must never be reported as proof of all
legal configurations of the generic Scala class.

## 1. Source, dependency, and evidence boundaries

- Never modify `upstream/`, the locked V2 snapshot metadata, or generated
  reference artifacts while implementing a target.
- Every target records its V2 Scala source path(s), source commit, dependency
  family, closure root, and exact observation points.
- A target cannot be marked `ACCEPTED` from file presence, AST shape, a direct
  export, or a bounded smoke test. It needs V2 direct test, static checks,
  reference-SV evidence, differential behavior, and a traceable commit.
- V3 evidence may justify prioritization or reuse, but every reused target is
  revalidated against V2.
- Before coding a reused candidate, compare its V3 source path with V2. A V2
  deletion, split, merge, or relocation is recorded as `RETIRED`, `SPLIT`, or
  `RELOCATED` in the mapping manifest; it is never hidden by preserving an old
  filename.
- External dependencies are represented by family/closure mappings, not by
  mechanically creating one Python file for every Scala file. A family may
  cover several source files only when its boundary, parameters, and
  observation points are explicit and its coverage manifest lists every
  covered child.

## 2. Target file contract

Each maintained Python hardware file uses UTF-8 without BOM, LF line endings,
four-space indentation, two blank lines between top-level definitions, and
the following ordered zones. Empty zones remain as a named comment when the
contract requires the zone:

1. `Module Contract`
2. `Configuration`
3. `Implementation`
4. `Public Adapter`
5. `Direct Entry`

The module docstring has one concise English line and one concise Chinese line.
`__all__` is explicit and contains only supported public symbols. Each
function/method definition has an immediately preceding one-line bilingual
responsibility comment. Function names start with an ASCII letter, except
Python data-model methods and a path-qualified protocol exception recorded in
the manifest.

Target modules may import only Python standard library and Amaranth (including
its documented `lib` and backend APIs). They must not import sibling Build
files, the parent repository, Scala, generated SV, `importlib`, `runpy`, path
scanners, or network clients. Cross-family dependencies enter through explicit
constructor parameters, immutable configuration records, or public adapters.

New modules use the exact adapter signature:

```python
def build_verilog(configuration, injected_dependencies):
    ...
```

The adapter must be deterministic, side-effect free at import time, and must
return or emit only through the documented build contract. Direct tests may
load the exact file path, but target modules may not implement their own
dynamic loader.

## 3. Behavioral rewrite rules

- Preserve real ports, widths, signedness, reset polarity, clock domains,
  register enables, pipeline latency, queue ordering, arbitration priority,
  memory read/write semantics, and error/flush behavior.
- Do not replace an unknown or expensive block with a constant, empty module,
  unconstrained `Any`, or a fake protocol endpoint. If V2 behavior cannot yet
  be established, record `CONTRACT_ONLY` with the missing evidence and stop
  promotion.
- Preserve parameter defaults and legal ranges from V2. Configuration values
  must be explicit and serializable; no hidden host/environment probing.
- For stateful families, write a small executable reference model or a
  transaction-level oracle and compare reset, steady state, boundary,
  backpressure, flush, and error cases. Use randomized vectors only after
  deterministic corner cases are present.
- Parent closure tests may exercise child implementations, but the manifest
  must name the child instances and prove that each child's externally
  observable contract is covered.

## 4. UHSC localization and naming

The Scala source and locked reference names remain unchanged. Localization is
performed only in project-owned generated HDL wrappers, manifests, and
external product-facing adapters. The auxiliary repository is also the
staging area for files that will later be copied into the main repository, so
core XiangShan targets use the final `Build-<hardware ID>-Hardware.py` naming
and directory layout from the moment they are created. External dependency
families may still use one family Build file with an explicit child manifest,
instead of one file per Scala source:

- The external processor identity is `UHSC` (Unifier Hardware System CPU).
- The only default external HDL prefix is `UHSC` (Unifier Hardware System
  CPU); the canonical local top wrapper is `UHSCTop`.
- Project-owned CPU/difftest identity strings may use `UHSC`; `XIANGSHAN`,
  `XiangShan`, `KMHV2`, and `XS` remain in source provenance, reference paths,
  comments, or explicit compatibility metadata. This is a localized external
  naming exception, not a change to the global product naming contract.
- Internal signal names, protocol field names, and standard external names
  (RISC-V, AXI, TileLink, CHI, JTAG, Rocket-Chip, Amaranth) are not renamed
  unless the user explicitly authorizes it or an external interface requires
  the change.
- No blind textual replacement is allowed. Every renamed symbol gets a
  `source_name`, `local_name`, `visibility`, and `reason` entry in the naming
  manifest, and all references are updated atomically.
- Core auxiliary paths follow `python/Program-System/System-Build/Build-Cpu/`
  and the corresponding source-traceable Build basename, for example
  `Build-Cpu.Backend.Fu.SRT16Divider-Hardware.py`.
- A temporary path under `python/ported/` is allowed only during an active
  relocation transaction. It must be removed in the same commit as the Build
  path creation, and all evidence/manifests must point to the Build path.
- No old alias, wrapper, or symlink is retained after the relocation commit.

## 5. Verification and commit discipline

For every batch, the worker must run, in order:

1. UTF-8/LF, AST parse, `py_compile`, and the five-zone/function-comment
   contract audit.
2. Exact-path import and deterministic `build_verilog` smoke.
3. Family direct tests covering the declared vectors/transactions.
4. V2 reference extraction or locked-SV comparison at the same observation
   points.
5. Differential result with trace/hash evidence, plus Verilator/Yosys checks
   where applicable.

The worker writes machine-readable JSON evidence and a mapping update, never
silently changes status, and commits only its owned files. The coordinator
reviews the diff, reruns the focused command, and pushes one coherent batch.
Generated SV, VCD/FST, caches, and temporary adapters stay ignored or under
the ignored `.agents` evidence area.

## 5A. Tiered verification and cached tool gates

The required evidence is tiered by closure size. A leaf or pure utility batch
must run the static contract, exact-path import, `py_compile`, and deterministic
direct/reference checks; it does not run a fresh Verilator/Yosys compile unless
the batch is selected for spot review. Stateful families and all parent
closures additionally require locked-reference differential, Verilator, and
Yosys. The UHSC top and complete Kunminghu hierarchy run these full gates only
at explicit milestones or after a child change invalidates the milestone.

Tool output is content-addressed under the ignored
`.agents/xiangshan-v2/validation/.cache/<sha256>/` directory. The key includes
target bytes, serialized configuration, command, tool version, and locked
reference hash; a hit is reusable only when all fields match exactly.

Leaf verification code should stay at or below 0.4 times the implementation's
effective lines; family and parent batches use a 1.0 upper bound. Exceptions
are recorded in evidence. Workers commit implementation, tests, evidence, and
mapping together; standalone hash-refresh commits are not a normal batch.
Non-overlapping implementation may continue while a coordinator performs a
focused spot check. A failed spot check escalates that batch and adjacent
dependent batches to full validation.

Progress is tracked on two independent rails: `STRUCTURE_VERIFIED` for exact
port/direction/width, hierarchy, and synthesis gates, and
`BEHAVIOR_VERIFIED_<family>` for direct and locked-reference behavior. These
rails improve visibility but never grant `ACCEPTED`; complete parent closure,
license review, UHSC localization, and user approval remain mandatory.

## 5B. Rewrite-freeze basic gates and placement

The rewrite phase is completed before the expensive family and parent
differential phase. Every planned Build file must first pass a cheap basic
gate in the auxiliary repository: UTF-8/LF and format audit, AST parse,
`py_compile`, exact-path import, Pyright for the owned batch, and deterministic
same-name `build_verilog(configuration, injected_dependencies)` export. The
export must parse without syntax errors and its top module name must match the
Build contract. This gate proves that the file is usable as a Build subject; it
does not prove behavioral equivalence.

Pyright compatibility directives that disable whole diagnostic classes are not
an acceptable freeze result. A worker may use a narrow, justified type cast or
an explicit protocol stub at the exact dynamic Amaranth boundary, but the
owned batch must finish with zero Pyright errors without file-level blanket
suppression. Any non-zero diagnostic count is recorded as a failed gate and
the Build remains outside `STRUCTURE_VERIFIED` until repaired.

During rewrite freeze, workers may batch many disjoint Build files and may
reuse one shared basic-gate runner. They must not create a separate full
Verilator/Yosys or locked-reference harness for every file. Family and parent
verification begins only after the planned Build set has passed the basic gate
or has an explicit `CONTRACT_ONLY`/`CONDITIONAL` record with its missing
evidence.

The auxiliary repository keeps migration-only differential validators,
reference extraction, hashes, evidence JSON, generated SV, waveforms, tool
logs, and caches under `.agents/xiangshan-v2/validation/`. These scripts are
not product modules and must not be imported by a Build file. Reusable,
one-to-one direct tests may be staged during development under the auxiliary
`python/Program-System/System-Testing/Testing-Cpu/` tree; they are ordinary
test subjects, not acceptance evidence, and must load only the local Build
path. After user approval and `ACCEPTED`, those tests may be adapted into the
main repository's `Program-System/System-Testing/Testing-Cpu/` and registered
in `Manifest-Testing-Hardware.py`, one direct test per formal Build subject.
Family/parent differential harnesses remain traceability tools in the
auxiliary repository unless separately approved as a stable test subject.

`Program-System/System-Output/` stores only controller-generated, ignored
logic artifacts and does not become a second test or evidence source.

## 5C. Yosys-readable view of a locked reference

`validation/reference-sv/` holds 1976 locked Chisel artifacts. 1204 of them carry
`automatic`, and the block-local form (`automatic logic [1:0] _GEN_3;` inside an
`always` block) is rejected by the installed `Yosys 0.52` even under
`read_verilog -sv`, which prints `Executing Verilog-2005 frontend` and aborts on
`TOK_AUTOMATIC`. `equiv_make` needs both sides in one design, so without a view
those modules cannot receive a complete-equivalence proof at all. No lossless
converter (`sv2v`, `slang`, `surelog`, `verific`) is installed; Verilator 5.032
does parse the originals.

The accepted workaround is a **synthesizable view** built in an ASCII temporary
work directory, never written back, limited to:

1. dropping the three non-synthesis conditional regions
   (`` `ifndef SYNTHESIS ``, `` `ifdef ENABLE_INITIAL_REG_ `` and
   `` `ifdef ENABLE_INITIAL_MEM_ ``), asserting that no unbalanced preprocessor
   text survives;
2. hoisting each block-local `automatic` declaration to module scope as a `reg`
   of identical width and name; where the declaration carries an initializer
   (`automatic logic [2:0] x = expr;`), the hoisted `reg` replaces the statement
   and the original line becomes the bare assignment `x = expr;`;
3. renaming only the reference module for the equivalence pair.

A validator using a view must enforce and record all of the following, and must
fail the run if any is false:

- `sources.reference_sv` still names the untouched locked file with its real
  digest, plus a `reference_lock` block carrying the `XSTop` digest;
- a multiplicity-preserving line-conservation gate: every code line that
  disappeared is a hoisted declaration and every line that appeared is exactly
  its module-scope `reg` form or initializer assignment. The significant-line
  delta must equal the number of initialized declarations, because one
  declaration-with-initializer becomes one `reg` declaration plus one bare
  assignment;
- every register update equation survives unchanged;
- the locked original itself still lints under Verilator in the locked synthesis
  preprocessor context, proving the original was valid rather than silently
  replaced;
- two negative controls that independently perturb a target equation and a
  reference equation, each producing an explicit SAT counterexample or nonzero
  final unproven-cell result. Tool errors, timeouts, empty output, and mere
  absence of a success marker are failures, not successful controls.

Two Yosys usage facts measured on the installed build: `flatten` takes a module
*selection* and there is no `-top` option, so it must not run before the pair is
chosen — a bare `flatten` deletes the reference top and `equiv_make` then reports
`Can't find gold module`. And `equiv_make` has no `-hierarchy` option here: flatten
`REF_<module>` and `DUT_<module>` by selection, then pair them plainly.

Equivalence is claimed against that view. This is a frontend workaround, not a
relaxation of section 6: the locked artifact is never modified, and any
transformation beyond the three listed above remains prohibited. Where semantics
cannot be compared through such a view, the record stays `STRICT_PENDING` and the
central audit inventories it as an attempt rather than progress.

## 5D. Strict evidence audit contract

A Build increments the strict-complete numerator only when the central audit
rechecks a repository-contained evidence record against all of these gates:

- the validator, Python Build, every Build-declared Scala source, every locked
  reference variant, and every recursively used reference child are inside this
  repository and their SHA-256 digests match;
- the Build filename matches `build_id`, a Build is claimed by at most one
  counting record, and `LOCKED_VARIANTS` (when present) is the exact locked
  DefaultConfig `XSTop` scope. Duplicate or reference-less members fail;
- every declared static/ABI/deterministic/miter gate has status `PASS`, required
  `py_compile` and Pyright gates are present, and counting records contain empty
  strict `failures` and `unclosed` lists. Later parent, license, integration, and
  user-approval tasks belong in a distinct `acceptance_unclosed` field;
- SAT evidence carries success and no-assumption/free-input markers parsed from
  the complete tool output, not only a bounded log tail. Sequential evidence
  carries both complete-output equivalence markers plus a positive total cell
  count with every cell proven and zero unproven;
- aggregate evidence has one verified record per locked variant, exact aggregate
  coverage counts, and decisive target-side and reference-side negative
  controls. A partial family remains `STRICT_PENDING` even if some members pass.

Evidence written under an older or weaker schema is non-counting until its
validator is hardened and rerun. The numerator may decrease after an audit; it
must never be preserved by weakening a gate or rewriting a failed record as a
pass.

## 6. Prohibited shortcuts

- No one-Scala/one-Python requirement for external dependencies.
- No copying V3 status into V2 status.
- No full-top acceptance inferred from child smoke tests.
- No dynamic sibling imports, shell execution, network access, or environment
  dependent behavior in target modules.
- No changing the locked source to make a comparison pass.
- No marking `ACCEPTED` when a reference, differential, integration, license,
  or parent-closure gate is missing.
