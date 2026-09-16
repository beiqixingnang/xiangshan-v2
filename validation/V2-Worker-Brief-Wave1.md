# V2 rewrite worker brief — hierarchy-completion waves (2026-09-16)

This brief is the shared contract for every parallel implementation worker in the
hierarchy-completion waves (wave 1 added the NewCSR and Chisel primitive
families; later waves continue the same rules). It is subordinate to
`V2-Python-Amaranth-Rules.md` and `V2-Rewrite-Execution-Plan.md`; read both
before writing code.

New aggregate Build subjects are authorised by the "Hierarchy-completion wave
amendment (2026-09-16)" section of `V2-Rewrite-Execution-Plan.md`. If your
assignment needs a Build path that is not listed there, stop and report instead
of inventing one — the coordinator registers paths.

## Working directory

`D:\知识库开发\Unifier-Hardware-System\.agents\xiangshan-v2`

Everything you write lands inside this directory. Never touch `upstream/`,
`.agents/xiangshan-v3*`, or the main repository at `../..`.

## Authoritative inputs

| Role | Path |
| --- | --- |
| Locked behavioural authority | `\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv` (228 MB, sha256 `8f279a52…`) |
| Locked hierarchy (modules, ports, children, Scala provenance) | `validation/v2-locked-hierarchy.json` |
| Per-module coverage status | `validation/v2-hierarchy-coverage.json` |
| Vendored V2 Scala source | `upstream/src/main/scala/…`, `upstream/rocket-chip/…`, `upstream/utility/…`, `upstream/huancun/…`, `upstream/coupledL2/…`, `upstream/yunsuan/…`, `upstream/fudian/…` |
| Style examples that already pass every gate | any `python/Program-System/System-Build/Build-Cpu/**/Build-*-Hardware.py` |

Every `// <path>.scala:<line>` comment in the locked SV is a provenance fact.
`validation/v2-locked-hierarchy.json` already carries, per module: the exact ANSI
port list (name, direction, width) and the instantiated child list. Use it — do
not re-parse the 228 MB file by hand.

To read a module body from the locked SV:

```bash
export PATH="/usr/bin:/bin:$PATH"
wsl.exe -d Debian -- bash -lc "awk '/^module <Name>\(/,/^endmodule/' /home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
```

Run Verilator and Yosys through WSL — they are not on the Windows PATH:

```bash
wsl.exe -d Debian -- bash -lc 'verilator --lint-only -Wno-fatal <files> -I<dir>'
wsl.exe -d Debian -- bash -lc 'yosys -p "read_verilog -sv <files>; hierarchy -top <mod>; proc; check"'
```

## File contract (non-negotiable)

UTF-8 without BOM, LF endings, four-space indent, two blank lines between
top-level definitions, and this zone order — each zone introduced by the exact
banner used elsewhere in the repository:

```python
# =============================================================================
# Module Contract
# =============================================================================
# =============================================================================
# Configuration
# =============================================================================
# =============================================================================
# Implementation
# =============================================================================
# =============================================================================
# Public Adapter
# =============================================================================
# =============================================================================
# Direct Entry
# =============================================================================
```

* Module docstring: one concise English line, then one concise Chinese line.
* `__all__` explicit, only supported public symbols.
* Every function/method gets an immediately preceding one-line **bilingual**
  responsibility comment (`# English. / 中文。`).
* Function and class names start with an ASCII letter; no leading underscore
  except Python data-model methods.
* Imports: standard library and Amaranth only. No sibling Build imports, no
  `importlib`/`runpy`, no path scanning, no network, no file reads at import
  time, no environment probing.
* Public adapter signature exactly:
  `def build_verilog(configuration, injected_dependencies):`
  It must be deterministic, side-effect free at import, and return the generated
  Verilog text.
* Keep the existing layout style of neighbouring files. Do not reformat, re-wrap,
  or re-indent code you did not have to change.

## Behaviour rules

* Preserve real ports, widths, signedness, reset polarity, clock domains,
  register enables, pipeline latency, queue ordering, arbitration priority,
  memory read/write semantics, and flush/error behaviour.
* Never replace an unknown or expensive block with a constant, an empty module,
  an unconstrained `Any`, or a fake endpoint. If V2 behaviour cannot be
  established, record `CONTRACT_ONLY` with the missing evidence and stop
  promotion.
* Follow `V2-Python-Amaranth-Rules.md` §3 for the local rewrite idioms in use:
  dynamic shift via a barrel shifter instead of `shift_left`, `Mux` instead of a
  Python `if` on a signal, `Array` for dynamic indexing, `_or_reduce`/`_and_reduce`
  style reductions where the Scala used reductions.
* Statuses you may write: `PYTHON_PRESENT`, `STRUCTURE_VERIFIED`,
  `DIRECT_TEST_PASS_BOUNDED`, `CONTRACT_ONLY`, `BLOCKED`. You may **not** write
  `BEHAVIOR_MATCHED`, `INTEGRATED`, or `ACCEPTED` — those stay locked.

## Verification you must run and record

```bash
export PATH="/usr/bin:/bin:$PATH"
PY="C:/Users/lishuo/.workbuddy/binaries/python/versions/3.13.12/python.exe"

# 1. static contract
$PY validation/v2-build-freeze-shared-audit.py          # shared sweep, all Build files
# 2. exact-path import + deterministic build_verilog smoke for your own file
$PY -c "import importlib.util,sys; s=importlib.util.spec_from_file_location('t',r'<your file>'); m=importlib.util.module_from_spec(s); sys.modules['t']=m; s.loader.exec_module(m); print(len(m.build_verilog({}, {})))"
# 3. Pyright must reach zero errors on your file
pyright.cmd --outputjson "<your file>"
```

Machine-readable evidence goes to `validation/<wave-id>-results.json` and must
record: the exact commands, the module list with per-module port counts taken
from `validation/v2-locked-hierarchy.json`, the generated-Verilog byte/hash
digest, the Verilator and Yosys verdicts, and every unclosed gate. Never record a
pass you did not observe.

## Prohibitions

* Do not modify `upstream/`, the main repository, another worker's files, or
  `validation/v2-locked-hierarchy.json`.
* Do not commit or push. The coordinator reviews the diff, re-runs the focused
  gates, and commits.
* Do not add a Build path outside the ones assigned to you.
* Do not leave targets under `python/ported/`.

## Report format

Return, in under 400 words: files written (with line counts), the covered locked
module list, the exact verification commands and their observed verdicts,
generated-Verilog digest, and every gate still open or failed. If you could not
establish a behaviour, say so explicitly rather than describing an intent.
