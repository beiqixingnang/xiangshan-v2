"""Prove the V2 FuncUnit catalog with a multiline-safe section 5C view.

The shared family rail deliberately recognizes only simple block-local
``automatic logic`` declarations.  FuncUnit's locked CIRCT output also uses
multidimensional packed shapes and multiline initializers.  This validator
keeps the shared proof machinery unchanged and supplies a stricter local view
that accounts for every disappeared and introduced effective line.
"""

from __future__ import annotations

from collections import Counter
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_strict_family_rail as rail  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Backend.Exu.FuncUnit-Hardware.py"
)
EVIDENCE = ROOT / "validation/v2-build-cpu-backend-exu-funcunit-strict-evidence.json"
BUILD_ID = "Build-Cpu.Backend.Exu.FuncUnit"
FAST_SEQUENTIAL_MEMBERS = {
    "Bku",
    "BlockCipherModule",
    "CryptoModule",
    "DivUnit",
    "ExeUnit",
}
DECLARATION_LEFT = re.compile(
    r"^(?P<shape>(?:\[[^\]]+\]\s*)*)(?P<name>[A-Za-z_]\w*)"
    r"(?P<suffix>(?:\s*\[[^\]]+\])*)$"
)


def _remove_ignored_regions(lines: list[str]) -> tuple[list[str], dict[str, int]]:
    """Remove only the three section 5C non-synthesis regions."""

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
) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    """Hoist block-local declarations without changing expression lines."""

    rewritten: list[str] = []
    declarations: list[str] = []
    disappeared: list[str] = []
    introduced_assignments: list[str] = []
    initialized_names: list[str] = []
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
            declaration = "reg " + head
            declarations.append(declaration)
            disappeared.append(first)
            index = end + 1
            continue

        left, right = head.split("=", 1)
        parsed = DECLARATION_LEFT.fullmatch(left.strip())
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
        introduced_assignments.append(replacement)
        initialized_names.append(name)
        index = end + 1
    return rewritten, declarations, disappeared, introduced_assignments, initialized_names


def synthesizable_view(text: str, top: str, rename: bool) -> tuple[str, dict[str, Any]]:
    """Apply the locked section 5C transform with exact effective-line accounting."""

    if rail.module_declaration(text, top) is None:
        raise AssertionError(f"locked top declaration missing for {top}")
    locked_lines = [
        line for line in (rail.strip_line(raw) for raw in text.split("\n")) if line
    ]
    lines, removed = _remove_ignored_regions(locked_lines)
    residual = [line for line in lines if "`" in line]
    keyed_patterns = [
        line for line in lines
        if re.search(r"'\{\s*(?:default|[A-Za-z_]\w*)\s*:", line)
    ]
    if keyed_patterns:
        raise AssertionError(f"keyed assignment pattern is outside section 5C: {top}")
    pattern_disappeared: list[str] = []
    pattern_appeared: list[str] = []
    pattern_lines: list[str] = []
    for line in lines:
        normalized_pattern = line.replace("'{", "{")
        if normalized_pattern != line:
            if line.startswith("automatic logic "):
                raise AssertionError("assignment-pattern and declaration rewrites overlap")
            pattern_disappeared.append(line)
            pattern_appeared.append(normalized_pattern)
        pattern_lines.append(normalized_pattern)
    rewritten, declarations, expected_disappeared, assignments, initialized = (
        _rewrite_automatic_declarations(pattern_lines)
    )
    body = "\n".join(rewritten)
    declaration_text = "\n".join(declarations) + ("\n" if declarations else "")
    normalized = (
        rail.insert_declarations(body, declaration_text, top) if declarations else body
    )
    view_lines = [line for line in normalized.split("\n") if line.strip()]
    locked_counts = Counter(lines)
    view_counts = Counter(view_lines)
    disappeared = list((locked_counts - view_counts).elements())
    appeared = list((view_counts - locked_counts).elements())
    expected_appeared = pattern_appeared + declarations + assignments
    conserved = (
        Counter(disappeared) == Counter(pattern_disappeared + expected_disappeared)
        and Counter(appeared) == Counter(expected_appeared)
        and len(view_lines) == len(lines) + len(initialized)
    )
    registers_before = re.findall(r"^\s*[A-Za-z_]\w*\s*<=\s*.+;$", "\n".join(lines), re.M)
    registers_after = re.findall(r"^\s*[A-Za-z_]\w*\s*<=\s*.+;$", normalized, re.M)
    audit: dict[str, Any] = {
        "top": top,
        "renamed_top": rename,
        "regions_removed_lines": removed,
        "block_local_temporaries_hoisted": [
            re.sub(r"^reg\s+(?:(?:\[[^\]]+\]\s*)+)?", "", item).rstrip(";")
            for item in declarations
        ],
        "initialized_declarations_hoisted": initialized,
        "positional_packed_patterns_normalized": len(pattern_disappeared),
        "code_lines_locked": len(lines),
        "code_lines_view": len(view_lines),
        "residual_preprocessor_directives": len(residual),
        "line_conservation_ok": conserved,
        "register_update_equations_locked": len(registers_before),
        "register_update_equations_preserved": registers_before == registers_after,
        "view_trusted": bool(
            conserved
            and registers_before == registers_after
            and not rail.BLOCK_LOCAL_ANY.search(normalized)
            and not residual
        ),
    }
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
    """Describe one exact repository-contained validator source."""

    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": rail.sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _rail_path() -> Path:
    """Return the imported shared rail path after an explicit type guard."""

    source = rail.__file__
    if source is None:
        raise RuntimeError("shared family rail has no source path")
    return Path(source).resolve()


def _validator_pyright_check() -> dict[str, Any]:
    """Analyze the validator together with its exact imported rail."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_funcunit_validator_pyright_"))
    try:
        validator_copy = temporary / Path(__file__).name
        rail_copy = temporary / _rail_path().name
        shutil.copyfile(Path(__file__).resolve(), validator_copy)
        shutil.copyfile(_rail_path(), rail_copy)
        command = [
            "cmd.exe", "/d", "/c", "pyright", "--outputjson",
            validator_copy.name,
        ]
        result = subprocess.run(
            command,
            cwd=temporary,
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
            "status": (
                "PASS"
                if result.returncode == 0 and summary.get("errorCount") == 0
                else "FAIL"
            ),
            "version": parsed.get("version") if isinstance(parsed, dict) else None,
            "error_count": summary.get("errorCount"),
            "files_analyzed": summary.get("filesAnalyzed"),
            "diagnostics": (
                parsed.get("generalDiagnostics", [])
                if isinstance(parsed, dict)
                else []
            ),
            "stderr_tail": result.stderr[-600:],
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"status": "FAIL", "error": repr(error)}
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


class FuncUnitRail(rail.FamilyRail):
    """Keep giant sequential members bounded while retaining explicit failures."""

    def prove(self, item: dict[str, Any]) -> dict[str, Any]:
        """Use direct sequential SAT first for the five largest locked closures."""

        if not item["sequential"] or item["name"] not in FAST_SEQUENTIAL_MEMBERS:
            result = super().prove(item)
            proof = result.get("yosys_equiv")
            if isinstance(proof, dict) and (
                proof.get("returncode") != 0 or proof.get("timed_out") is True
            ):
                proof["formal_success_marker"] = False
            return result

        name = item["name"]
        pair = " ".join(
            rail.shlex.quote(rail.wsl_path(path))
            for path in (item["target"], item["reference"])
        )
        lint = rail.run_wsl([
            "verilator", "--lint-only", "-Wno-fatal", "--top-module",
            f"{name}_MITER", rail.wsl_path(item["target"]),
            rail.wsl_path(item["reference"]), rail.wsl_path(item["miter"]),
        ])
        locked_lint = rail.run_wsl(
            ["verilator", "--lint-only", "-Wno-fatal", "-DSYNTHESIS", "--top-module", name]
            + [rail.wsl_path(path) for path in item["locked_sources"]]
        )
        script = (
            f"read_verilog -sv {pair}; proc; async2sync; memory; opt; "
            f"flatten REF_{name}; flatten DUT_{name}; "
            f"equiv_make REF_{name} DUT_{name} {name}_EQUIV; "
            f"prep -top {name}_EQUIV; equiv_simple -undef -short -seq 1; "
            "equiv_status -assert"
        )
        proof = rail.run_wsl(["yosys", "-Q", "-p", script], timeout=180)
        markers = proof.get("equiv_success_markers", {})
        proof["markers_present"] = markers
        proof["formal_success_marker"] = (
            proof.get("returncode") == 0
            and isinstance(markers, dict)
            and bool(markers)
            and all(markers.values())
        )
        if isinstance(proof.get("equiv_cells_full"), int):
            proof["equiv_cells"] = proof["equiv_cells_full"]
        summary = proof.get("equiv_summary_full")
        if isinstance(summary, list) and len(summary) == 2:
            proof["proven_cells"], proof["unproven_cells"] = summary
        if isinstance(proof.get("equiv_failed_full"), int):
            proof["unproven_cells"] = proof["equiv_failed_full"]
        if not proof["formal_success_marker"]:
            proof["status"] = "FAIL"
        return {
            "method": "sequential_equivalence",
            "verilator": lint,
            "locked_verilator": locked_lint,
            "yosys_equiv": proof,
        }

    def aggregate(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Prove all combinational members while accepting identical shared children."""

        subset = [item for item in items if not item["sequential"]]
        lines = [f"module {self.build_id.split('.')[-1]}_AGG("]
        for item in subset:
            for port, width in item["inputs"].items():
                qualified = f"{item['name']}_{port}"
                lines.append(
                    f"  input [{width - 1}:0] {qualified},"
                    if width > 1
                    else f"  input {qualified},"
                )
        lines.extend(("  output mismatch", ");"))
        terms: list[str] = []
        for index, item in enumerate(subset):
            term = f"m{index}"
            terms.append(term)
            lines.append(f"  wire {term};")
            connections = [
                f".{port}({item['name']}_{port})" for port in item["inputs"]
            ]
            connections.append(f".mismatch({term})")
            lines.extend((
                f"  {item['name']}_MITER mit{index}(",
                "    " + ", ".join(connections),
                "  );",
            ))
        lines.extend((
            "  assign mismatch = " + " | ".join(terms) + ";",
            "endmodule",
        ))
        glue_text = "\n".join(lines) + "\n"
        glue = self.work / f"{self.build_id.split('.')[-1]}_AGG.sv"
        glue.write_text(glue_text, encoding="utf-8", newline="\n")
        if not rail.nets_declared(glue_text):
            raise AssertionError("aggregate glue drives nets it never declares")
        sources = " ".join(
            rail.shlex.quote(rail.wsl_path(path))
            for item in subset
            for path in (item["target"], item["reference"], item["miter"])
        )
        script = (
            f"read_verilog -sv -overwrite {sources} "
            f"{rail.shlex.quote(rail.wsl_path(glue))}; "
            f"prep -top {glue.stem}; flatten; opt; sat -prove mismatch 0"
        )
        proof = rail.run_wsl(["yosys", "-Q", "-p", script])
        proof["formal_success_marker"] = proof.get("sat_success_marker") is True
        proof["unconstrained"] = proof.get("unconstrained_marker") is True
        proof["mitered_variants"] = len(subset)
        proof["shared_reference_module_policy"] = "IDENTICAL_LOCKED_VIEW_OVERWRITE"
        counts = proof.get("sat_counts_full")
        if isinstance(counts, list) and len(counts) == 2:
            proof["sat_variables"], proof["sat_clauses"] = counts
        if not proof["formal_success_marker"] or not proof["unconstrained"]:
            proof["status"] = "FAIL"
        return proof

    def negative_control(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Use the already-proven small HashModule as the sequential control."""

        ordered = sorted(
            items,
            key=lambda item: (item["name"] != "HashModule", item["name"]),
        )
        control = super().negative_control(ordered)
        sample = next(item for item in ordered if item["name"] == "HashModule")
        source = sample["target"].read_text(encoding="utf-8")
        top = "DUT_HashModule"
        module_start = re.search(r"\bmodule\s+" + top + r"\s*\(", source)
        if module_start is None:
            return control
        module_end = source.find("endmodule", module_start.end())
        body = source[module_start.start():module_end]
        mutated_body, count = re.subn(
            r"(\.[A-Za-z_]\w*\s*\()\s*io_out\s*(\))",
            r"\1uhsc_mutated_io_out\2",
            body,
            count=1,
        )
        if count == 1:
            mutated_body += (
                "  wire [63:0] uhsc_mutated_io_out;\n"
                "  assign io_out = ~uhsc_mutated_io_out;\n"
            )
            mutant = self.work / "MUTANT_sequential_target_child_output.sv"
            mutant.write_text(
                source[:module_start.start()] + mutated_body + source[module_end:],
                encoding="utf-8",
                newline="\n",
            )
            pair = " ".join(
                rail.shlex.quote(rail.wsl_path(path))
                for path in (mutant, sample["reference"])
            )
            script = (
                f"read_verilog -sv {pair}; proc; async2sync; memory; opt; "
                "flatten REF_HashModule; flatten DUT_HashModule; "
                "equiv_make REF_HashModule DUT_HashModule HashModule_EQUIV; "
                "prep -top HashModule_EQUIV; equiv_induct -undef; equiv_status -assert"
            )
            verdict = rail.run_wsl(["yosys", "-Q", "-p", script])
            explicit_failure = verdict.get("equiv_failure_marker") is True
            still = all(verdict.get("equiv_success_markers", {}).values())
            detected = (
                isinstance(verdict.get("returncode"), int)
                and explicit_failure
                and not still
            )
            control["cases"]["sequential.target"] = {
                "status": "PASS" if detected else "FAIL",
                "control_entry": "HashModule",
                "control_port": "io_out",
                "mutation_applied": True,
                "explicit_failure_marker": explicit_failure,
                "success_marker_still_present": still,
                "returncode": verdict.get("returncode"),
            }
        control["status"] = (
            "PASS"
            if all(case.get("status") == "PASS" for case in control["cases"].values())
            else "FAIL"
        )
        return control


def main() -> int:
    """Run the FuncUnit family proof and persist an independently locked record."""

    rail.synthesizable_view = synthesizable_view
    runner = FuncUnitRail(BUILD, BUILD_ID, EVIDENCE)
    payload = runner.run()
    validator_path = Path(__file__).resolve()
    validator_pyright = _validator_pyright_check()
    payload["validator"] = validator_path.relative_to(ROOT).as_posix()
    payload["sources"]["validator"] = _source_record(validator_path)
    payload["sources"]["validator_dependencies"] = {
        "strict_family_rail": _source_record(_rail_path())
    }
    payload["checks"]["pyright"]["validator"] = validator_pyright
    payload["view_policy"] = {
        "status": "PASS",
        "kind": "SECTION_5C_MULTILINE_AUTOMATIC_AND_POSITIONAL_PACKED_VIEW",
        "locked_sources_written": False,
        "line_conservation_required": True,
        "register_update_equations_required": True,
    }
    if validator_pyright.get("status") != "PASS":
        payload["failures"].append("FuncUnit validator pyright")
        payload["unclosed"] = ["strict gates did not all pass"]
        payload["status"] = "STRICT_PENDING"
        payload["strict_complete_eligible"] = False
        payload["strict_complete_count_delta"] = 0
        payload["acceptance_eligible"] = False
    EVIDENCE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "status": payload["status"],
        "strict_complete_count_delta": payload["strict_complete_count_delta"],
        "entries": payload["scope"]["variant_count"],
        "proven": payload["checks"]["catalog_coverage"]["proven"],
        "negative_control": payload["checks"]["negative_control"]["status"],
        "failure_count": len(payload["failures"]),
        "first_failures": payload["failures"][:10],
    }, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
