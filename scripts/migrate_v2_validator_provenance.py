"""Move validator provenance reads from Build attributes to auxiliary JSON."""

from __future__ import annotations

import ast
import json
import py_compile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "validation"

STANDARD_FILES = (
    "v2-age-family-validator.py",
    "v2-backend-rob-rename-trace-family-validator.py",
    "v2-backend-vector-datapath-family-validator.py",
    "v2-bypass-pipe-family-validator.py",
    "v2-dcache-miss-family-validator.py",
    "v2-debug-family-validator.py",
    "v2-decode-control-family-validator.py",
    "v2-difftest-state-family-validator.py",
    "v2-vector-memory-family-validator.py",
    "v2-store-family-validator.py",
    "v2-prefetch-family-validator.py",
    "v2-pmp-family-validator.py",
    "v2-floating-point-family-validator.py",
    "v2-newcsr-control-family-validator.py",
    "v2-intbuffer-family-validator.py",
    "v2_frontend_icache_prefetch_family_validator.py",
    "v2_top_xstile_intbuffer_validator.py",
)
MEMORY_FILE = "v2-memory-mmu-lsq-family-validator.py"
TL_CHILDREN_FILE = "v2_top_l2top_tl_children_validator.py"


def insert_import(text: str, names: str) -> str:
    """Insert one local validation-helper import after standard imports."""

    statement = f"from v2_build_provenance import {names}"
    if statement in text:
        return text
    anchors = ("from typing import Any\n", "from pathlib import Path\n")
    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + f"\n{statement}\n", 1)
    raise ValueError("no stable import anchor")


def migrate_standard(path: Path) -> dict[str, object]:
    """Replace a standard one-Build validator provenance read."""

    original = path.read_text(encoding="utf-8")
    occurrences = original.count("module.SOURCE_PATHS")
    if occurrences == 0:
        return {"path": path.name, "status": "ALREADY_MIGRATED"}
    updated = original.replace("module.SOURCE_PATHS", "source_paths_for_build(TARGET)")
    updated = insert_import(updated, "source_paths_for_build")
    path.write_text(updated, encoding="utf-8", newline="\n")
    return {"path": path.name, "status": "UPDATED", "replacements": occurrences}


def migrate_memory(path: Path) -> dict[str, object]:
    """Replace provenance reads inside the two-Build memory validator loop."""

    original = path.read_text(encoding="utf-8")
    occurrences = original.count("module.SOURCE_PATHS")
    if occurrences == 0:
        return {"path": path.name, "status": "ALREADY_MIGRATED"}
    updated = original.replace("module.SOURCE_PATHS", "source_paths_for_build(path)")
    updated = insert_import(updated, "source_paths_for_build")
    path.write_text(updated, encoding="utf-8", newline="\n")
    return {"path": path.name, "status": "UPDATED", "replacements": occurrences}


def migrate_tl_children(path: Path) -> dict[str, object]:
    """Preserve the per-member source mapping used by the TL-child validator."""

    original = path.read_text(encoding="utf-8")
    occurrences = original.count("module.SOURCE_PATHS")
    if occurrences == 0:
        return {"path": path.name, "status": "ALREADY_MIGRATED"}
    expression = 'provenance_for_build(TARGET)["SOURCE_PATHS"]'
    updated = original.replace("module.SOURCE_PATHS", expression)
    updated = insert_import(updated, "provenance_for_build")
    path.write_text(updated, encoding="utf-8", newline="\n")
    return {"path": path.name, "status": "UPDATED", "replacements": occurrences}


def main() -> int:
    """Apply the validator migration as one rollback-safe transaction."""

    paths = [VALIDATION / name for name in STANDARD_FILES]
    paths.extend((VALIDATION / MEMORY_FILE, VALIDATION / TL_CHILDREN_FILE))
    originals = {path: path.read_bytes() for path in paths}
    records = []
    try:
        for path in paths[:-2]:
            records.append(migrate_standard(path))
        records.append(migrate_memory(paths[-2]))
        records.append(migrate_tl_children(paths[-1]))
        for path in paths:
            text = path.read_text(encoding="utf-8")
            ast.parse(text)
            py_compile.compile(str(path), doraise=True)
            if "module.SOURCE_PATHS" in text:
                raise AssertionError(f"Build provenance read remains: {path}")
    except BaseException:
        for path, original in originals.items():
            path.write_bytes(original)
        raise
    print(json.dumps({"status": "PASS", "records": records}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
