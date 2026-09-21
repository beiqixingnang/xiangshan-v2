"""Focused strict rail for the Rocket JTAG state and TAP references.

The locked CIRCT output for ``JtagStateMachine`` contains one block-local
``automatic logic`` initializer whose expression is spread over several
physical lines.  Yosys rejects that declaration, while Verilator accepts the
untouched locked source.  This validator builds a temporary section-5C view
with an explicit line-conservation audit and then delegates ABI, lint, formal,
and two-sided negative-control checks to :mod:`v2_strict_family_rail`.

The focused result is intentionally non-counting: the product Build is a
catalog with additional members, so proving these two names alone cannot move
the aggregate strict numerator.
"""

from __future__ import annotations

from collections import Counter
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_strict_family_rail as rail  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Dependency.Utility.ResidualFamily-Hardware.py"
)
DIRECT_TEST = ROOT / (
    "python/Program-System/System-Testing/Testing-Cpu/"
    "Testing-Cpu.Dependency.Utility.ResidualFamily-Hardware.py"
)
EVIDENCE = ROOT / "validation/v2-jtag-reference-view-results.json"
MEMBERS = ("JtagStateMachine", "JtagTapController")

_DECLARATION_LEFT = re.compile(
    r"^(?P<shape>(?:\[[^\]]+\]\s*)*)(?P<name>[A-Za-z_]\w*)"
    r"(?P<suffix>(?:\s*\[[^\]]+\])*)$"
)
_REGISTER_UPDATE = re.compile(r"^\s*[A-Za-z_]\w*\s*<=\s*.+;$")


def _remove_ignored_regions(lines: list[str]) -> tuple[list[str], dict[str, int]]:
    """Drop only the three explicitly permitted non-synthesis regions."""

    removed: dict[str, int] = {}
    for opening in rail.REMOVED_REGIONS:
        while True:
            start = next((index for index, line in enumerate(lines) if opening in line), None)
            if start is None:
                break
            end = rail.directive_block_end(lines, start)
            removed[opening] = removed.get(opening, 0) + end - start
            lines = lines[:start] + lines[end:]
    return lines, removed


def _rewrite_automatic_declarations(
    lines: list[str],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Hoist block locals while preserving every expression line verbatim.

    A declaration is recognized only when its first significant line starts
    with ``automatic logic``.  The statement may continue until its first
    semicolon.  For an initialized declaration, only that first line is
    replaced with ``name =``; all following expression lines remain in the
    output.  Multiline uninitialized declarations are rejected because their
    lossless module-scope form cannot be established by this narrow parser.
    """

    rewritten: list[str] = []
    declarations: list[str] = []
    disappeared: list[str] = []
    assignments: list[str] = []
    index = 0
    while index < len(lines):
        first = lines[index]
        if not first.startswith("automatic logic "):
            rewritten.append(first)
            index += 1
            continue

        end = index
        while end < len(lines) and ";" not in lines[end]:
            end += 1
        if end >= len(lines):
            raise AssertionError("unterminated automatic logic declaration")
        statement = lines[index:end + 1]
        head = first[len("automatic logic "):]
        if "=" not in head:
            if len(statement) != 1:
                raise AssertionError("multiline uninitialized declaration is outside section 5C")
            declarations.append("reg " + head)
            disappeared.append(first)
            index = end + 1
            continue

        left, right = head.split("=", 1)
        parsed = _DECLARATION_LEFT.fullmatch(left.strip())
        if parsed is None:
            raise AssertionError(f"unsupported automatic declaration: {first}")
        name = parsed.group("name")
        shape = parsed.group("shape").strip()
        suffix = parsed.group("suffix").strip()
        declaration = "reg " + (shape + " " if shape else "") + name
        if suffix:
            declaration += suffix
        declarations.append(declaration + ";")
        replacement = name + " =" + ((" " + right.strip()) if right.strip() else "")
        rewritten.append(replacement)
        rewritten.extend(statement[1:])
        disappeared.append(first)
        assignments.append(replacement)
        index = end + 1
    return rewritten, declarations, disappeared, assignments


def synthesizable_view(text: str, top: str, rename: bool) -> tuple[str, dict[str, Any]]:
    """Create a conservative, source-counted Yosys-readable reference view."""

    if rail.module_declaration(text, top) is None:
        raise AssertionError(f"locked top declaration missing for {top}")
    lines = [line for line in (rail.strip_line(raw) for raw in text.split("\n")) if line]
    lines, removed = _remove_ignored_regions(lines)
    residual = [line for line in lines if "`" in line]

    # JTAG references do not use assignment patterns.  Refuse all of them
    # rather than applying a context-dependent rewrite that could widen 5C.
    pattern_lines = [line for line in lines if "'{" in line]
    if pattern_lines:
        raise AssertionError(f"assignment pattern is outside focused JTAG 5C view: {top}")

    rewritten, declarations, disappeared_declarations, assignments = (
        _rewrite_automatic_declarations(lines)
    )
    body = "\n".join(rewritten)
    declaration_text = "\n".join(declarations) + ("\n" if declarations else "")
    normalized = rail.insert_declarations(body, declaration_text, top) if declarations else body

    view_lines = [line for line in normalized.split("\n") if line.strip()]
    locked_counts = Counter(lines)
    view_counts = Counter(view_lines)
    disappeared = list((locked_counts - view_counts).elements())
    appeared = list((view_counts - locked_counts).elements())
    expected_appeared = declarations + assignments
    initialized_count = len(assignments)
    conserved = (
        Counter(disappeared) == Counter(disappeared_declarations)
        and Counter(appeared) == Counter(expected_appeared)
        and len(view_lines) == len(lines) + initialized_count
    )
    registers_before = _REGISTER_UPDATE.findall("\n".join(lines))
    registers_after = _REGISTER_UPDATE.findall(normalized)
    audit: dict[str, Any] = {
        "top": top,
        "renamed_top": rename,
        "regions_removed_lines": removed,
        "block_local_temporaries_hoisted": [
            re.sub(r"^reg\s+(?:(?:\[[^\]]+\]\s*)+)?", "", item).rstrip(";")
            for item in declarations
        ],
        "initialized_declarations_hoisted": [item.split(" =", 1)[0] for item in assignments],
        "positional_packed_patterns_normalized": 0,
        "code_lines_locked": len(lines),
        "code_lines_view": len(view_lines),
        "residual_preprocessor_directives": len(residual),
        "line_conservation_ok": conserved,
        "register_update_equations_locked": len(registers_before),
        "register_update_equations_preserved": registers_before == registers_after,
    }
    audit["view_trusted"] = bool(
        conserved
        and audit["register_update_equations_preserved"]
        and not rail.BLOCK_LOCAL_ANY.search(normalized)
        and not residual
        and not pattern_lines
    )
    if rename:
        normalized, count = re.subn(
            r"\bmodule\s+" + re.escape(top) + r"\s*\(",
            f"module REF_{top}(",
            normalized,
            count=1,
        )
        if count != 1:
            raise AssertionError(f"locked top declaration missing for {top}")
    return normalized + "\n", audit


def _source_record(path: Path) -> dict[str, Any]:
    """Return a repository-contained source identity for evidence."""

    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": rail.sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _pyright(path: Path) -> dict[str, Any]:
    """Run Pyright on one exact validator source."""

    command = ["cmd.exe", "/d", "/c", "pyright", "--outputjson", str(path)]
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
    )
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        parsed = {}
    summary = parsed.get("summary", {}) if isinstance(parsed, dict) else {}
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 and summary.get("errorCount") == 0 else "FAIL",
        "error_count": summary.get("errorCount"),
        "files_analyzed": summary.get("filesAnalyzed"),
        "stderr_tail": result.stderr[-600:],
    }


def main() -> int:
    """Run focused JTAG checks and write non-counting evidence."""

    import py_compile

    py_compile.compile(str(BUILD), doraise=True)
    py_compile.compile(str(DIRECT_TEST), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)

    # Keep the shared rail unchanged on disk; this process-local substitution
    # supplies only the stricter multiline view for this focused family.
    rail.synthesizable_view = synthesizable_view
    module = rail.load_module("jtag_reference_view", BUILD)
    focused = rail.FamilyRail(BUILD, "JtagReferenceView", EVIDENCE)
    shutil.rmtree(focused.work, ignore_errors=True)
    focused.work.mkdir(parents=True, exist_ok=True)
    items = [focused.prepare(module, name) for name in MEMBERS]
    results = [focused.prove(item) for item in items]
    negative = focused.negative_control(items)

    direct = subprocess.run(
        [sys.executable, str(DIRECT_TEST), "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
    )
    pyright = _pyright(Path(__file__).resolve())

    records: list[dict[str, Any]] = []
    failures: list[str] = []
    for item, result in zip(items, results, strict=True):
        proof = result.get("yosys_equiv") or result.get("sat_miter") or {}
        formal_ok = (
            item["abi_exact"]
            and item["deterministic"]
            and item["view_trusted"]
            and result["verilator"].get("status") == "PASS"
            and result["locked_verilator"].get("status") == "PASS"
            and proof.get("status") == "PASS"
            and proof.get("formal_success_marker") is True
            and proof.get("unproven_cells", 0) == 0
        )
        records.append({
            "member": item["name"],
            "abi_exact": item["abi_exact"],
            "deterministic_export": item["deterministic"],
            "reference_view_trusted": item["view_trusted"],
            "view_audits": item["view_audits"],
            "children": item["children"],
            "target_verilator": result["verilator"].get("status"),
            "locked_reference_verilator": result["locked_verilator"].get("status"),
            "formal_method": result["method"],
            "formal_status": "PASS" if formal_ok else "PENDING",
            "formal_tool_status": proof.get("status"),
            "formal_success_marker": proof.get("formal_success_marker"),
            "equiv_cells": proof.get("equiv_cells"),
            "unproven_cells": proof.get("unproven_cells"),
            "diagnostic_tail": proof.get("output_tail", "")[-2000:],
        })
        if not formal_ok:
            failures.append(item["name"] + ": focused formal gates incomplete")

    if direct.returncode != 0:
        failures.append("direct test failed")
    if negative.get("status") != "PASS":
        failures.append("two-sided negative control failed")
    if pyright.get("status") != "PASS":
        failures.append("validator pyright failed")

    all_formal = not failures
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_JTAG_REFERENCE_VIEW_FOCUSED",
        "source_commit": rail.SOURCE_COMMIT,
        "status": "PASS_FOCUSED_NOT_COUNTED" if all_formal else "STRICT_PENDING",
        "strict_complete_count_delta": 0,
        "acceptance_eligible": False,
        "build": BUILD.relative_to(ROOT).as_posix(),
        "direct_test": DIRECT_TEST.relative_to(ROOT).as_posix(),
        "members": list(MEMBERS),
        "direct_test_status": "PASS" if direct.returncode == 0 else "FAIL",
        "direct_test_output": (direct.stdout + direct.stderr)[-2000:],
        "records": records,
        "negative_control": negative,
        "checks": {"py_compile": "PASS", "pyright": pyright},
        "sources": {
            "validator": _source_record(Path(__file__).resolve()),
            "python_build": _source_record(BUILD),
            "shared_rail": _source_record(Path(rail.__file__).resolve()),
            "declared_scala_sources": rail.declared_scala_sources(BUILD),
            "locked_reference": {
                name: _source_record(ROOT / "validation/reference-sv" / f"{name}.sv")
                for name in MEMBERS
            },
        },
        "reference_lock": {
            "directory": "validation/reference-sv",
            "xstop_sha256": rail.XSTOP_SHA256,
            "locked_references_written": False,
            "sha256_by_module": {
                name: rail.sha256_file(ROOT / "validation/reference-sv" / f"{name}.sv")
                for name in MEMBERS
            },
        },
        "view_policy": {
            "status": "PASS",
            "kind": "SECTION_5C_MULTILINE_AUTOMATIC_DECLARATION_ONLY",
            "line_conservation_required": True,
            "register_update_equations_required": True,
            "assignment_patterns": "REJECTED_UNLESS_PROVEN",
            "locked_sources_written": False,
        },
        "failures": failures,
        "unclosed": [
            "Focused proof does not cover the remaining catalog members; aggregate Build remains pending.",
        ],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "status": payload["status"],
        "formal": {record["member"]: record["formal_status"] for record in records},
        "negative_control": negative.get("status"),
        "strict_complete_count_delta": 0,
        "failures": failures,
    }, ensure_ascii=False))
    return 0 if all_formal else 1


if __name__ == "__main__":
    raise SystemExit(main())
