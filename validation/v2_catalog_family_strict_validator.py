"""Run the shared strict family rail against one catalog-style Build file.

Usage: ``python validation/v2_catalog_family_strict_validator.py --build <path>``

The Build path may be given relative to the repository or as a glob-unique file
name fragment.  The build id comes from the Build filename, the evidence path is
derived from it, and the Scala provenance is taken from the sources that Build
itself declares.  Everything else -- member enumeration, the 5C view, the SAT or
inductive rail per member, the aggregate miter and the two-sided negative control
-- lives in ``v2_strict_family_rail``.
"""

from __future__ import annotations

import argparse
import json
import re
import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from v2_strict_family_rail import (  # noqa: E402
    ROOT, FamilyRail, enumerate_members, load_module, pyright_check,
)


NAMING_MANIFEST = ROOT / "UHSC-Naming-Manifest.json"


def naming_records() -> list[dict[str, str]]:
    """Read the explicit path transaction; never discover Build identities."""

    payload = json.loads(NAMING_MANIFEST.read_text(encoding="utf-8"))
    return payload["path_rename_transaction"]["renames"]


def resolve_build(text: str) -> Path:
    """Resolve a Build path or a unique filename fragment."""

    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = (ROOT / text)
    declared = [ROOT / record["new_path"] for record in naming_records()
                if record["kind"] == "build-script"]
    if candidate.resolve() in {path.resolve() for path in declared} and candidate.is_file():
        return candidate.resolve()
    matches = sorted(path for path in declared if text in path.name)
    if len(matches) != 1:
        raise SystemExit(f"'{text}' resolved to {len(matches)} Build files; give a unique fragment")
    return matches[0]


def build_id_for(path: Path) -> str:
    """Derive the build_id from the Build filename, as the rail's convention does."""

    relative = path.resolve().relative_to(ROOT).as_posix()
    entries = [record for record in naming_records()
               if record["kind"] == "build-script" and record["new_path"] == relative]
    if len(entries) != 1:
        raise ValueError("Build identity is absent or duplicated in the path manifest")
    return entries[0]["build_id"]


def direct_path_for(path: Path) -> Path:
    """Resolve this Build's unique direct test from the same path transaction."""

    identity = build_id_for(path).removeprefix("Build-Cpu.")
    expected_name = "Testing-Cpu-" + identity + "-Hardware.py"
    matches = [ROOT / record["new_path"] for record in naming_records()
               if record["kind"] == "testing-script"
               and Path(record["new_path"]).name == expected_name]
    if len(matches) != 1 or not matches[0].is_file():
        raise ValueError("Build lacks a unique registered direct test: " + identity)
    return matches[0]


def source_record(path: Path) -> dict[str, object]:
    """Bind an exact current source to the proof receipt."""

    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size}


def preflight_only(runner: FamilyRail, direct: dict[str, object], output: Path) -> int:
    """Diagnose prerequisites without launching any formal or changing strict evidence."""

    module = load_module("catalog_preflight", runner.build_path)
    members = enumerate_members(module, runner.build_path)
    pyright = pyright_check(runner.build_path)
    results = []
    for name in members:
        item = runner.prepare(module, name)
        failures = runner.cheap_static_failures(item)
        if direct["status"] != "PASS":
            failures.append("direct test is missing or failed")
        if pyright.get("status") != "PASS":
            failures.append("Pyright failed")
        if not failures:
            lint, reference_lint = runner.lint_gate(item)
            if lint.get("status") != "PASS" or reference_lint.get("status") != "PASS":
                failures.append("DUT or locked-reference lint failed")
        results.append({"member": name, "status": "READY_FOR_FORMAL" if not failures else "BLOCKED",
                        "failures": failures, "abi_exact": item["abi_exact"],
                        "deterministic": item["deterministic"], "view_trusted": item["view_trusted"]})
    payload = {"kind": "V2_STRICT_PREFLIGHT_DIAGNOSTIC", "build_id": runner.build_id,
               "strict_count_delta": 0, "formal": "NOT_RUN", "direct_test": direct,
               "members": results, "ready_members": sum(not row["failures"] for row in results),
               "member_count": len(results), "status": "PREFLIGHT_COMPLETE"}
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8", newline="\n")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def main() -> int:
    """Prove one catalog Build and print its verdict."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, help="Build file path or unique name fragment")
    parser.add_argument("--evidence", help="evidence file name under validation/")
    parser.add_argument("--build-id", help="override the derived build_id")
    parser.add_argument("--preflight-only", action="store_true",
                        help="write diagnostic prerequisites only; do not run formal or overwrite a proof")
    parser.add_argument(
        "--scala", action="append", default=[],
        help="vendored upstream Scala source used for provenance (repeatable)",
    )
    arguments = parser.parse_args()
    build_path = resolve_build(arguments.build)
    build_id = arguments.build_id or build_id_for(build_path)
    if build_id != build_id_for(build_path):
        raise ValueError("Build identity override conflicts with the explicit manifest")
    try:
        direct_path = direct_path_for(build_path)
    except ValueError:
        if not arguments.preflight_only:
            raise
        direct_path = None
    slug = re.sub(r"\W+", "-", build_id.lower()).strip("-")
    if arguments.evidence and Path(arguments.evidence).name != arguments.evidence:
        raise ValueError("evidence must be a filename inside validation")
    evidence = ROOT / "validation" / (arguments.evidence or f"v2-{slug}-strict-evidence.json")
    scala_paths = [
        (ROOT / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
        for value in arguments.scala
    ]
    missing = [str(path) for path in scala_paths if not path.is_file()]
    if missing:
        raise SystemExit(f"Scala provenance path is missing: {', '.join(missing)}")
    if not scala_paths:
        provenance = json.loads((ROOT / "validation/v2-build-provenance-map.json").read_text(encoding="utf-8"))
        record = provenance["entries"].get(build_path.relative_to(ROOT).as_posix(), {})
        declared_paths = record.get("SOURCE_SCALA_PATHS", [])
        if not declared_paths:
            source_map = record.get("SOURCE_PATHS", {})
            declared_paths = [relative for values in source_map.values()
                              for relative in (values if isinstance(values, list) else [values])]
        scala_paths = [ROOT / relative for relative in declared_paths]
    runner = FamilyRail(build_path, build_id, evidence,
                        scala_path=scala_paths[0] if scala_paths else None)
    if direct_path is None:
        direct_record: dict[str, object] = {"status": "MISSING_DIRECT_TEST", "returncode": None}
        return preflight_only(runner, direct_record,
                              ROOT / "validation" / f"v2-{slug}-preflight-results.json")
    direct = subprocess.run([sys.executable, "-B", str(direct_path)], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if arguments.preflight_only:
        direct_record = {"status": "PASS" if direct.returncode == 0 else "FAIL",
                         "returncode": direct.returncode,
                         "command": [sys.executable, "-B", direct_path.relative_to(ROOT).as_posix()]}
        return preflight_only(runner, direct_record,
                              ROOT / "validation" / f"v2-{slug}-preflight-results.json")
    if direct.returncode != 0:
        print((direct.stdout + direct.stderr)[-1800:])
        raise SystemExit("Direct test failed; formal was not started")
    payload = runner.run()
    payload["validator"] = Path(__file__).resolve().relative_to(ROOT).as_posix()
    payload["sources"]["validator"] = source_record(Path(__file__).resolve())
    payload["sources"]["validator_dependencies"] = {
        "strict_family_rail": source_record(ROOT / "validation/v2_strict_family_rail.py"),
        "direct_test": source_record(direct_path),
    }
    payload["sources"]["declared_scala_sources"] = {
        path.relative_to(ROOT).as_posix(): {"vendored": True, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in scala_paths
    }
    payload["checks"]["direct_test"] = {
        "status": "PASS", "returncode": direct.returncode,
        "command": [sys.executable, "-B", direct_path.relative_to(ROOT).as_posix()],
        "output_tail": (direct.stdout + direct.stderr)[-1800:],
    }
    payload["acceptance_eligible"] = False
    evidence.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    scope = payload["scope"]
    print(json.dumps({
        "build": build_path.relative_to(ROOT).as_posix(),
        "build_id": build_id,
        "evidence": evidence.relative_to(ROOT).as_posix(),
        "status": payload["status"],
        "strict_complete_count_delta": payload["strict_complete_count_delta"],
        "entries": scope["variant_count"],
        "combinational": scope["combinational_variants"],
        "sequential": scope["sequential_variants"],
        "aggregate_input_bits": scope["aggregate_input_bits"],
        "proven": payload["checks"]["catalog_coverage"]["proven"],
        "negative_control": payload["checks"]["negative_control"]["status"],
        "failure_count": len(payload["failures"]),
        "first_failures": payload["failures"][:6],
    }, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
