"""Compact migratable Build port catalogs without changing their ordered ABI."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BEGIN_MARKER = "# BEGIN LOCKED PORT CATALOG"
END_MARKER = "# END LOCKED PORT CATALOG"


def load_module(path: Path, suffix: str) -> Any:
    """Load one Build at its exact path under a unique temporary name."""

    name = "compact_ports_" + hashlib.sha1(
        (path.as_posix() + suffix).encode()
    ).hexdigest()
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def normalize_catalog(module: Any) -> dict[str, tuple[tuple[str, str, int], ...]]:
    """Return an ordered, immutable ABI mapping from a loaded Build."""

    value = getattr(module, "PORT_SPECS", None)
    if not isinstance(value, dict) or not value:
        value = getattr(module, "LOCKED_PORT_SPECS", None)
    if not isinstance(value, dict) or not value:
        raise ValueError("Build exposes no non-empty PORT_SPECS mapping")
    normalized: dict[str, tuple[tuple[str, str, int], ...]] = {}
    for member, rows in value.items():
        if not isinstance(member, str) or not member:
            raise ValueError(f"invalid member name: {member!r}")
        converted: list[tuple[str, str, int]] = []
        for row in rows:
            if isinstance(row, (list, tuple)) and len(row) == 3:
                name, direction, width = row
            elif all(hasattr(row, field) for field in ("name", "direction", "width")):
                name, direction, width = row.name, row.direction, row.width
            else:
                raise ValueError(f"{member}: invalid port row {row!r}")
            item = (str(name), str(direction), int(width))
            if item[1] not in ("input", "output") or item[2] < 1:
                raise ValueError(f"{member}: invalid port row {item!r}")
            converted.append(item)
        normalized[member] = tuple(converted)
    return normalized


def catalog_digest(catalog: dict[str, tuple[tuple[str, str, int], ...]]) -> str:
    """Hash the exact member order and ordered ABI rows."""

    encoded = json.dumps(
        list((member, list(rows)) for member, rows in catalog.items()),
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def render_catalog(catalog: dict[str, tuple[tuple[str, str, int], ...]]) -> str:
    """Render one compact, readable literal row per irregular port."""

    lines = [
        "PortSpec = tuple[str, str, int]",
        "",
        "PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {",
    ]
    for member, rows in catalog.items():
        lines.append(f"    {member!r}: (")
        lines.extend(
            f"        ({name!r}, {direction!r}, {width}),"
            for name, direction, width in rows
        )
        lines.append("    ),")
    lines.append("}")
    return "\n".join(lines) + "\n\n"


def assigned_name(node: ast.stmt) -> str | None:
    """Return a top-level simple assignment target name."""

    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
        return target.id if isinstance(target, ast.Name) else None
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def replacement_span(text: str) -> tuple[int, int]:
    """Find the complete generated catalog assignment region."""

    lines = text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if BEGIN_MARKER in line]
    ends = [index for index, line in enumerate(lines) if END_MARKER in line]
    if starts or ends:
        if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
            raise ValueError("unbalanced locked catalog markers")
        start_line = starts[0]
        end_line = ends[0] + 1
        while end_line < len(lines) and re.fullmatch(
            r"\s*(?:PORT_SPECS\s*=\s*LOCKED_PORT_SPECS\s*)?\r?\n?",
            lines[end_line],
        ):
            end_line += 1
        return sum(map(len, lines[:start_line])), sum(map(len, lines[:end_line]))

    tree = ast.parse(text)
    candidates = [
        node for node in tree.body
        if assigned_name(node) in ("PORT_SPECS", "LOCKED_PORT_SPECS")
    ]
    if not candidates:
        raise ValueError("catalog assignment not found")
    preferred = next(
        (node for node in candidates if assigned_name(node) == "LOCKED_PORT_SPECS"),
        candidates[0],
    )
    if preferred.end_lineno is None:
        raise ValueError("catalog assignment has no end position")
    aliases = [
        node
        for node in tree.body
        if assigned_name(node) == "PortSpec" and node.lineno < preferred.lineno
    ]
    first = min(aliases, key=lambda node: node.lineno) if aliases else preferred
    start = sum(map(len, lines[:first.lineno - 1])) + first.col_offset
    end_line_text = lines[preferred.end_lineno - 1]
    end = sum(map(len, lines[:preferred.end_lineno - 1])) + len(end_line_text.rstrip("\r\n"))
    return start, end


def compact(path: Path) -> dict[str, Any]:
    """Rewrite one catalog and roll back if its runtime ABI changes."""

    original_bytes = path.read_bytes()
    original = original_bytes.decode("utf-8")
    before = normalize_catalog(load_module(path, "_before"))
    start, end = replacement_span(original)
    replacement = render_catalog(before)
    updated = original[:start] + replacement + original[end:]
    updated = updated.replace("PORT_SPECS = LOCKED_PORT_SPECS\n", "")
    updated = updated.replace("PORT_SPECS = LOCKED_PORT_SPECS\r\n", "")
    updated = re.sub(r"\bLOCKED_PORT_SPECS\b", "PORT_SPECS", updated)
    while re.search(r"(['\"]PORT_SPECS['\"])\s*,\s*['\"]PORT_SPECS['\"]", updated):
        updated = re.sub(
            r"(['\"]PORT_SPECS['\"])\s*,\s*['\"]PORT_SPECS['\"]",
            r"\1",
            updated,
        )
    path.write_text(updated, encoding="utf-8", newline="\n")
    try:
        after = normalize_catalog(load_module(path, "_after"))
        if before != after:
            raise AssertionError("expanded ordered ABI changed")
        if "LOCKED_PORT_SPECS" in updated or BEGIN_MARKER in updated or END_MARKER in updated:
            raise AssertionError("migration-only catalog marker remains")
    except BaseException:
        path.write_bytes(original_bytes)
        raise
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "members": len(before),
        "ports": sum(len(rows) for rows in before.values()),
        "ordered_abi_sha256": catalog_digest(before),
        "before_lines": len(original.splitlines()),
        "after_lines": len(updated.splitlines()),
        "removed_lines": len(original.splitlines()) - len(updated.splitlines()),
        "status": "ABI_IDENTICAL",
    }


def main() -> int:
    """Compact every requested Build and print a machine-readable report."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Build paths relative to repository root")
    arguments = parser.parse_args()
    paths = [(ROOT / value).resolve() for value in arguments.paths]
    for path in paths:
        path.relative_to(ROOT.resolve())
        if not path.is_file():
            raise FileNotFoundError(path)
    originals = {path: path.read_bytes() for path in paths}
    records = []
    try:
        for path in paths:
            records.append(compact(path))
    except BaseException:
        for path, original in originals.items():
            path.write_bytes(original)
        raise
    print(json.dumps({"status": "PASS", "records": records}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
