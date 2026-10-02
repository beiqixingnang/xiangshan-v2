"""Inventory every vendored Scala file before freezing aggregate rewrite owners."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "upstream"
OUTPUT = ROOT / "validation/v2-all-source-scan-seed.json"
DECLARATION = re.compile(r"\b(class|object|trait)\s+([A-Za-z_$][\w$]*)")


def masked_scala(source: str) -> str:
    """Remove comments and string payloads while preserving source line numbers."""

    result = []
    index = 0
    block_depth = 0
    state = "code"
    while index < len(source):
        tail = source[index:]
        char = source[index]
        consumed = 1
        if state == "code":
            if tail.startswith("//"):
                state, consumed = "line", 2
            elif tail.startswith("/*"):
                state, block_depth, consumed = "block", 1, 2
            elif tail.startswith('"""'):
                state, consumed = "triple", 3
            elif char == '"':
                state = "string"
            else:
                result.append(char)
                index += 1
                continue
        elif state == "line" and char == "\n":
            state = "code"
        elif state == "block":
            if tail.startswith("/*"):
                block_depth, consumed = block_depth + 1, 2
            elif tail.startswith("*/"):
                block_depth, consumed = block_depth - 1, 2
                if not block_depth:
                    state = "code"
        elif state == "triple" and tail.startswith('"""'):
            state, consumed = "code", 3
        elif state == "string":
            if char == "\\":
                consumed = min(2, len(tail))
            elif char == '"':
                state = "code"
        result.extend("\n" if c == "\n" else " " for c in source[index:index + consumed])
        index += consumed
    return "".join(result)


def source_path(raw: str, available: set[str]) -> str | None:
    """Normalize historical paths only when they resolve to one vendored file."""

    raw = re.sub(r":\d+$", "", raw.replace("\\", "/"))
    candidates = [raw, "upstream/" + raw.removeprefix("upstream/")]
    if raw.startswith("scala/"):
        candidates.append("upstream/" + raw.removeprefix("scala/"))
    if "xs-v2-local/" in raw:
        candidates.append("upstream/" + raw.split("xs-v2-local/", 1)[1])
    exact = {value for value in candidates if value in available}
    if len(exact) == 1:
        return exact.pop()
    suffix = raw.removeprefix("scala/").removeprefix("upstream/")
    matches = [path for path in available if path.endswith("/" + suffix)]
    return matches[0] if len(matches) == 1 else None


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [item for child in value for item in strings(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in strings(child)]
    return []


def scan() -> dict[str, Any]:
    paths = sorted(UPSTREAM.rglob("*.scala"))
    available = {path.relative_to(ROOT).as_posix() for path in paths}
    old_mapping: dict[str, set[str]] = defaultdict(set)
    unresolved = []
    for filename, collection, target, source in (
        ("V2-Core-Rewrite-Inventory.json", "entries", "build_path", "source_scala"),
        ("V2-Dependency-Family-Inventory.json", "families", "plan_build_file", "source_paths"),
        ("validation/v2-build-provenance-map.json", "entries", None, None),
    ):
        data = json.loads((ROOT / filename).read_text(encoding="utf-8"))[collection]
        rows = data.items() if isinstance(data, dict) else ((row.get(target), row) for row in data)
        for owner, row in rows:
            if not owner:
                continue
            references = strings(row.get(source)) if source else strings(row)
            for raw in references:
                if not raw.endswith(".scala"):
                    continue
                resolved = source_path(raw, available)
                if resolved:
                    old_mapping[resolved].add(owner)
                else:
                    unresolved.append({"manifest": filename, "owner": owner, "source": raw})
    hierarchy = json.loads((ROOT / "validation/v2-locked-hierarchy.json").read_text(encoding="utf-8"))
    locked: dict[str, set[str]] = defaultdict(set)
    for module, row in hierarchy["modules"].items():
        for raw in row["scala_sources"]:
            resolved = source_path(raw, available)
            if resolved:
                locked[resolved].add(module)
    rows = []
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        source = data.decode("utf-8-sig")
        masked = masked_scala(source)
        package = re.search(r"^\s*package\s+([\w.]+)", masked, re.M)
        declarations = [{"kind": match[1], "name": match[2],
                         "line": masked.count("\n", 0, match.start()) + 1,
                         "extends_excerpt": masked[match.end():match.end() + 240].strip().split("\n", 1)[0][:180]}
                        for match in DECLARATION.finditer(masked)]
        rows.append({"path": relative, "root": path.relative_to(UPSTREAM).parts[0],
                     "sha256": hashlib.sha256(data).hexdigest(), "lines": len(source.splitlines()),
                     "package": package[1] if package else "", "declarations": declarations,
                     "hardware_markers": sorted(set(re.findall(
                         r"\b(?:Module|RawModule|Bundle|LazyModule|BlackBox|RegInit|RegEnable|RegNext|Reg|Mem|SyncReadMem|IO|Bool|UInt|SInt|Analog|Vec)\b", masked))),
                     "locked_modules": sorted(locked[relative]),
                     "historical_mapping_candidates_not_implementation": sorted(old_mapping[relative])})
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    return {"kind": "V2_ALL_SCALA_SOURCE_SCAN_SEED", "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
            "auxiliary_commit": git, "scope": "all vendored Scala, including tests, host generators, configuration and currently unused hardware",
            "source_file_count": len(rows), "by_root": dict(Counter(row["root"] for row in rows)),
            "declared_symbol_count": sum(len(row["declarations"]) for row in rows),
            "locked_source_file_count": sum(bool(row["locked_modules"]) for row in rows),
            "unresolved_historical_source_mappings": unresolved,
            "policy": "Every file needs an explicit reviewed disposition; lexical markers and old mappings grant no implementation credit.",
            "files": rows, "coverage_complete": False, "acceptance_eligible": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    payload = scan()
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: payload[key] for key in (
        "source_file_count", "by_root", "declared_symbol_count", "locked_source_file_count")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
