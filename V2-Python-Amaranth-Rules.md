# Kunminghu V2 Python/Amaranth rewrite rules

This file is the execution contract for the V2 rewrite. It is subordinate to
the repository's `Program-Document/Document-Spec/Hardware-System-Specification.md`.
The vendored V2 Scala tree and its generated SystemVerilog are the only
behavioral authority. Existing V3 Python is reusable source material, never a
V2 acceptance oracle.

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

## 6. Prohibited shortcuts

- No one-Scala/one-Python requirement for external dependencies.
- No copying V3 status into V2 status.
- No full-top acceptance inferred from child smoke tests.
- No dynamic sibling imports, shell execution, network access, or environment
  dependent behavior in target modules.
- No changing the locked source to make a comparison pass.
- No marking `ACCEPTED` when a reference, differential, integration, license,
  or parent-closure gate is missing.
