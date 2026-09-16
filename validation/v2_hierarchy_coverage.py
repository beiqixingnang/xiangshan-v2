"""V2 locked-hierarchy coverage: which locked modules have a Python counterpart.

锁定层级覆盖度：哪些锁定模块已有 Python 对应实现。

Read-only migration tooling.  It joins the pinned ``XSTop.sv`` hierarchy
inventory with the two rewrite inventories and the landed Build subjects, and
emits a per-module status.  It never modifies product code.
"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HIER = ROOT / "validation/v2-locked-hierarchy.json"
CORE = ROOT / "V2-Core-Rewrite-Inventory.json"
FAMILY = ROOT / "V2-Dependency-Family-Inventory.json"
OUT = ROOT / "validation/v2-hierarchy-coverage.json"


def key(path: str) -> str:
    """Reduce any Scala provenance path to its canonical ``<pkg>/...`` tail."""
    text = str(path).split(":")[0].replace("\\", "/")
    marker = "src/main/scala/"
    index = text.find(marker)
    return text[index + len(marker):] if index >= 0 else text


def as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def main() -> int:
    hierarchy = json.loads(HIER.read_text(encoding="utf-8"))
    modules = hierarchy["modules"]

    core = json.loads(CORE.read_text(encoding="utf-8"))
    family = json.loads(FAMILY.read_text(encoding="utf-8"))

    core_subject: dict[str, str] = {}
    for entry in core["entries"]:
        for source in as_list(entry.get("source_scala")) + as_list(entry.get("reference_surface")):
            core_subject[key(source)] = entry["id"]
    family_subject: dict[str, str] = {}
    for fam in family["families"]:
        for source in as_list(fam.get("source_paths")):
            family_subject.setdefault(key(source), fam["family_id"])
    conditional = {key(p) for fam in family["families"]
                   for p in as_list(fam.get("conditional_or_inlined_paths"))}

    rows = []
    for name, node in sorted(modules.items()):
        sources = sorted({key(s) for s in node["scala_sources"]})
        core_ids = sorted({core_subject[s] for s in sources if s in core_subject})
        fam_ids = sorted({family_subject[s] for s in sources if s in family_subject})
        if core_ids:
            status = "CORE_BOUNDED_SUBJECT"
        elif fam_ids:
            status = "FAMILY_SUBJECT"
        else:
            status = "MISSING"
        rows.append({
            "module": name,
            "status": status,
            "ports": node["port_count"],
            "children": node["child_count"],
            "scala_sources": sources[:6],
            "core_subjects": core_ids,
            "family_subjects": fam_ids,
            "conditional_or_inlined": any(s in conditional for s in sources),
        })

    counts = collections.Counter(r["status"] for r in rows)
    missing_by_scala = collections.Counter(
        s for r in rows if r["status"] == "MISSING" for s in r["scala_sources"]
    )
    out = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_HIERARCHY_COVERAGE",
        "source_inventory": "validation/v2-locked-hierarchy.json",
        "reference_sha256": hierarchy["reference_sha256"],
        "locked_module_count": len(rows),
        "status_counts": dict(counts),
        "row_count": len(rows),
        "rows": rows,
        "missing_top_scala": [
            {"scala": s, "modules": n} for s, n in missing_by_scala.most_common(60)
        ],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({
        "locked_modules": len(rows),
        "status": dict(counts),
        "missing_scala_files": len(missing_by_scala),
        "core_subjects_seen": len({i for r in rows for i in r["core_subjects"]}),
        "family_subjects_seen": len({i for r in rows for i in r["family_subjects"]}),
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
