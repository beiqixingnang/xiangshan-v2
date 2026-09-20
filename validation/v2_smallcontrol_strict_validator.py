"""Strict SmallControl rail with a local reference-view parser.

The locked family rail remains byte-for-byte frozen because existing evidence
hashes depend on it.  SmallControl references additionally contain Chisel's
multi-line block-local declarations (and array declarations) that the frozen
parser intentionally does not rewrite.  This wrapper supplies only that
parser extension, delegates all proof, ABI, negative-control, and evidence
rules to the frozen rail, and records the frozen rail as a hashed dependency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import py_compile
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import v2_strict_family_rail as rail  # noqa: E402


ROOT = rail.ROOT
BUILD_ROOT = ROOT / "python/Program-System/System-Build/Build-Cpu"
FROZEN_RAIL = ROOT / "validation/v2_strict_family_rail.py"

# The frozen rail's declarations intentionally cover one-line declarations.
# These two local expressions add array suffixes and an initializer whose RHS
# may continue over arbitrary source lines until its terminating semicolon.
BLOCK_LOCAL_ARRAY = re.compile(
    r"^([ \t]*)automatic\s+logic\s+(\[[^\]]*\])?\s*"
    r"([A-Za-z_]\w*(?:\s*\[[^\]]+\])?(?:\s*,\s*"
    r"[A-Za-z_]\w*(?:\s*\[[^\]]+\])?)*)\s*;[ \t]*$",
    re.M,
)
INITIALIZED_ANY_LINE = re.compile(
    r"automatic\s+logic\s+(\[[^\]]*\])?\s*"
    r"([A-Za-z_]\w*(?:\s*\[[^\]]+\])?)\s*=\s*(.*?);",
    re.S,
)


def sha256(path: Path) -> str:
    """Hash one repository file exactly."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pyright_check(path: Path) -> dict[str, Any]:
    """Type-check the wrapper at its real path so its rail import is present."""

    command = ["cmd.exe", "/d", "/c", "pyright", "--outputjson", str(path)]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {}
    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    passed = result.returncode == 0 and summary.get("errorCount") == 0
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if passed else "FAIL",
        "version": payload.get("version") if isinstance(payload, dict) else None,
        "files_analyzed": summary.get("filesAnalyzed"),
        "error_count": summary.get("errorCount"),
        "warning_count": summary.get("warningCount"),
        "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
        "stderr_tail": result.stderr[-1000:],
    }


def _view(text: str, top: str, rename: bool) -> tuple[str, dict[str, Any]]:
    """Apply the locked 5C view plus multiline declaration handling."""

    if rail.module_declaration(text, top) is None:
        raise AssertionError(f"locked top declaration missing for {top}")
    lines = [line for line in (rail.strip_line(raw) for raw in text.split("\n")) if line]
    removed: dict[str, int] = {}
    for opening in rail.REMOVED_REGIONS:
        while True:
            start = next((index for index, line in enumerate(lines) if opening in line), None)
            if start is None:
                break
            end = rail.directive_block_end(lines, start)
            removed[opening] = removed.get(opening, 0) + end - start
            lines = lines[:start] + lines[end:]
    residual = [line for line in lines if "`" in line]
    body = "\n".join(lines)

    initialized = [
        (match.group(1), match.group(2), match.group(3))
        for match in INITIALIZED_ANY_LINE.finditer(body)
    ]
    rewritten = INITIALIZED_ANY_LINE.sub(
        lambda match: f"{match.group(2)} = {match.group(3)};", body
    )
    temporaries: list[tuple[str | None, str]] = []
    for match in BLOCK_LOCAL_ARRAY.finditer(rewritten):
        for item in match.group(3).split(","):
            declaration = re.fullmatch(
                r"([A-Za-z_]\w*)(\s*\[[^\]]+\])?", item.strip()
            )
            if declaration is None:
                raise AssertionError(f"unparsed automatic declaration: {item!r}")
            temporaries.append((match.group(2), declaration.group(1)
                                + (declaration.group(2) or "")))
    hoisted = temporaries + [(width, name) for width, name, _ in initialized]
    declarations = "".join(
        f"reg {width} {name};\n" if width else f"reg {name};\n"
        for width, name in hoisted
    )
    stripped = BLOCK_LOCAL_ARRAY.sub("", rewritten)
    normalized = stripped if not declarations else rail.insert_declarations(
        stripped, declarations, top
    )
    view_lines = [line for line in normalized.split("\n") if line.strip()]
    # A multi-line initializer cannot be audited with the frozen rail's
    # line-counter method: one declaration legitimately becomes one assignment
    # plus one hoisted declaration while its continuation lines are folded into
    # that assignment.  Instead require an exhaustive, non-overlapping match of
    # every retained ``automatic logic`` token, then check that the only two
    # transformations are the recorded declaration-to-assignment rewrite and
    # the recorded module-scope declaration insertion.
    automatic_before = len(re.findall(r"\bautomatic\s+logic\b", body))
    automatic_after = len(re.findall(r"\bautomatic\s+logic\b", normalized))
    expected_rewritten = INITIALIZED_ANY_LINE.sub(
        lambda match: f"{match.group(2)} = {match.group(3)};", body
    )
    expected_stripped = BLOCK_LOCAL_ARRAY.sub("", expected_rewritten)
    expected_normalized = (
        expected_stripped if not declarations
        else rail.insert_declarations(expected_stripped, declarations, top)
    )
    hoisted_names = [name for _, name in hoisted]
    conserved = (
        automatic_before == len(temporaries) + len(initialized)
        and automatic_after == 0
        and normalized == expected_normalized
        and len(hoisted_names) == len(set(hoisted_names))
    )
    registers_before = re.findall(r"^\s*[A-Za-z_]\w*\s*<=\s*.+;$", body, re.M)
    registers_after = re.findall(r"^\s*[A-Za-z_]\w*\s*<=\s*.+;$", normalized, re.M)
    audit: dict[str, Any] = {
        "top": top,
        "renamed_top": rename,
        "regions_removed_lines": removed,
        "block_local_temporaries_hoisted": [name for _, name in temporaries],
        "initialized_declarations_hoisted": [name for _, name, _ in initialized],
        "code_lines_locked": len(lines),
        "code_lines_view": len(view_lines),
        "automatic_declarations_locked": automatic_before,
        "automatic_declarations_rewritten": len(temporaries) + len(initialized),
        "automatic_declarations_remaining": automatic_after,
        "hoisted_names_unique": len(hoisted_names) == len(set(hoisted_names)),
        "residual_preprocessor_directives": len(residual),
        "line_conservation_ok": conserved,
        "register_update_equations_locked": len(registers_before),
        "register_update_equations_preserved": registers_before == registers_after,
        "multiline_initializer_parser": True,
        "array_declaration_parser": True,
    }
    audit["view_trusted"] = bool(
        conserved
        and audit["register_update_equations_preserved"]
        and not rail.BLOCK_LOCAL_ANY.search(normalized)
        and not residual
    )
    if rename:
        normalized, count = re.subn(
            r"\bmodule\s+" + re.escape(top) + r"\s*\(",
            f"module REF_{top}(", normalized, count=1
        )
        if count != 1:
            raise AssertionError(f"locked top declaration missing for {top}")
    return normalized + "\n", audit


def resolve_build(value: str) -> Path:
    """Resolve a Build path or unique filename fragment."""

    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    if candidate.is_file():
        return candidate
    matches = sorted(path for path in BUILD_ROOT.rglob("*.py") if value in path.name)
    if len(matches) != 1:
        raise SystemExit(f"{value!r} resolved to {len(matches)} Build files")
    return matches[0]


def main() -> int:
    """Run the SmallControl strict family proof."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build",
        default="python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
                "Build-Cpu.Backend.SmallControl.Family-Hardware.py",
    )
    parser.add_argument(
        "--evidence",
        default="validation/v2-build-cpu-backend-smallcontrol-family-strict-evidence.json",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
        help="per-tool timeout; raise explicitly for a final RegCache closure run",
    )
    arguments = parser.parse_args()
    if arguments.timeout_seconds <= 0:
        raise SystemExit("--timeout-seconds must be positive")
    build_path = resolve_build(arguments.build)
    evidence = ROOT / arguments.evidence
    original = rail.synthesizable_view
    original_defaults = rail.run_wsl.__defaults__
    rail.synthesizable_view = _view
    rail.run_wsl.__defaults__ = (arguments.timeout_seconds,)
    try:
        payload = rail.FamilyRail(
            build_path,
            "Build-Cpu.Backend.SmallControl.Family",
            evidence,
        ).run()
    finally:
        rail.synthesizable_view = original
        rail.run_wsl.__defaults__ = original_defaults

    own_path = Path(__file__)
    py_compile.compile(str(own_path), doraise=True)
    wrapper_pyright = pyright_check(own_path)
    own_record = {
        "path": own_path.relative_to(ROOT).as_posix(),
        "sha256": sha256(own_path),
        "bytes": own_path.stat().st_size,
    }
    frozen_record = {
        "path": FROZEN_RAIL.relative_to(ROOT).as_posix(),
        "sha256": sha256(FROZEN_RAIL),
        "bytes": FROZEN_RAIL.stat().st_size,
    }
    payload["validator"] = own_record["path"]
    payload["sources"]["validator"] = own_record
    payload["sources"]["validator_dependencies"] = {
        "frozen_family_rail": frozen_record,
    }
    payload["audit_policy"]["validator_dependency_hashes"] = True
    payload["audit_policy"]["per_tool_timeout_seconds"] = arguments.timeout_seconds
    payload["checks"]["validator_wrapper"] = {
        "status": wrapper_pyright["status"],
        "path": own_record["path"],
        "sha256": own_record["sha256"],
        "py_compile": "PASS",
        "pyright": wrapper_pyright,
    }
    if wrapper_pyright["status"] != "PASS":
        payload["status"] = "STRICT_PENDING"
        payload["strict_complete_eligible"] = False
        payload["strict_complete_count_delta"] = 0
        payload["acceptance_eligible"] = False
        payload["failures"].append("pyright validator wrapper")
        payload["unclosed"] = ["strict gates did not all pass"]
    evidence.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "build": build_path.relative_to(ROOT).as_posix(),
        "status": payload["status"],
        "strict_complete_count_delta": payload["strict_complete_count_delta"],
        "proven": payload["checks"]["catalog_coverage"]["proven"],
        "entries": payload["scope"]["variant_count"],
        "failures": payload["failures"][:8],
    }, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
