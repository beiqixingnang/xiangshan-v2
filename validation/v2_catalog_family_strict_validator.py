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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from v2_strict_family_rail import ROOT, FamilyRail  # noqa: E402


BUILD_ROOT = ROOT / "python/Program-System/System-Build/Build-Cpu"


def resolve_build(text: str) -> Path:
    """Resolve a Build path or a unique filename fragment."""

    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = (ROOT / text)
    if candidate.is_file():
        return candidate
    matches = sorted(path for path in BUILD_ROOT.rglob("*.py") if text in path.name)
    if len(matches) != 1:
        raise SystemExit(f"'{text}' resolved to {len(matches)} Build files; give a unique fragment")
    return matches[0]


def build_id_for(path: Path) -> str:
    """Derive the build_id from the Build filename, as the rail's convention does."""

    return re.sub(r"-Hardware\.py$", "", path.name)


def main() -> int:
    """Prove one catalog Build and print its verdict."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, help="Build file path or unique name fragment")
    parser.add_argument("--evidence", help="evidence file name under validation/")
    parser.add_argument("--build-id", help="override the derived build_id")
    arguments = parser.parse_args()
    build_path = resolve_build(arguments.build)
    build_id = arguments.build_id or build_id_for(build_path)
    slug = re.sub(r"\W+", "-", build_id.lower()).strip("-")
    evidence = ROOT / "validation" / (arguments.evidence or f"v2-{slug}-strict-evidence.json")
    payload = FamilyRail(build_path, build_id, evidence).run()
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
