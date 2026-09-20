"""Remove Build-local provenance constants only when runtime code does not use them."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import py_compile
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "python/Program-System/System-Build/Build-Cpu"
PROVENANCE_MAP = ROOT / "validation/v2-build-provenance-map.json"


def is_provenance_name(name: str) -> bool:
    """Identify migration metadata that belongs in auxiliary evidence."""

    upper = name.upper()
    if upper in {"HIERARCHY", "SOURCE_COMMIT", "LOCKED_REFERENCE_SHA256"}:
        return True
    if "SOURCE" not in upper:
        return False
    return any(
        token in upper
        for token in ("PATH", "ROOT", "FILE_COUNT", "COMMIT", "OBSERVATION")
    )


def assigned_names(node: ast.stmt) -> tuple[str, ...]:
    """Return simple names assigned by one top-level statement."""

    targets: list[ast.expr] = []
    if isinstance(node, ast.Assign):
        targets.extend(node.targets)
    elif isinstance(node, ast.AnnAssign):
        targets.append(node.target)
    return tuple(target.id for target in targets if isinstance(target, ast.Name))


def load_module(path: Path, suffix: str) -> Any:
    """Import a Build under an isolated temporary module name."""

    name = f"strip_provenance_{abs(hash((path.as_posix(), suffix)))}"
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


def public_snapshot(module: Any) -> dict[str, Any]:
    """Capture behavior-relevant public inventory without provenance values."""

    covered = tuple(getattr(module, "COVERED_MODULES", ()))
    ports = getattr(module, "PORT_SPECS", None)
    normalized_ports = None
    if isinstance(ports, dict):
        normalized_ports = tuple(
            (str(member), tuple(tuple(row) for row in rows))
            for member, rows in ports.items()
        )
    return {
        "covered_modules": covered,
        "port_specs": normalized_ports,
        "has_build_verilog": callable(getattr(module, "build_verilog", None)),
    }


def json_value(value: Any) -> Any:
    """Convert frozen metadata values to JSON-compatible structures."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, (list, tuple, set)):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    raise TypeError(f"unsupported provenance value: {type(value).__name__}")


def top_level_loads(tree: ast.Module) -> dict[str, list[ast.stmt]]:
    """Map each loaded name to the top-level statements containing its use."""

    result: dict[str, list[ast.stmt]] = {}
    for statement in tree.body:
        for node in ast.walk(statement):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                result.setdefault(node.id, []).append(statement)
    return result


def render_all(names: list[str]) -> str:
    """Render an explicit public-symbol list after metadata removal."""

    lines = ["__all__ = ["]
    lines.extend(f"    {name!r}," for name in names)
    lines.append("]")
    return "\n".join(lines)


def line_span(lines: list[str], node: ast.stmt) -> tuple[int, int]:
    """Return the full-line byte span for a top-level statement."""

    if node.end_lineno is None:
        raise ValueError("AST node lacks end line")
    start = sum(len(line) for line in lines[: node.lineno - 1])
    end = sum(len(line) for line in lines[: node.end_lineno])
    return start, end


def rewrite(path: Path, apply: bool) -> dict[str, Any]:
    """Plan or apply one safe provenance-only rewrite."""

    original_bytes = path.read_bytes()
    original = original_bytes.decode("utf-8")
    lines = original.splitlines(keepends=True)
    tree = ast.parse(original)
    assignments: dict[str, ast.stmt] = {}
    for statement in tree.body:
        for name in assigned_names(statement):
            if is_provenance_name(name):
                assignments[name] = statement
    if not assignments:
        return {"path": path.relative_to(ROOT).as_posix(), "status": "NO_ASSIGNMENTS"}

    loads = top_level_loads(tree)
    assignment_nodes = set(assignments.values())
    all_node = next(
        (
            statement
            for statement in tree.body
            if "__all__" in assigned_names(statement)
        ),
        None,
    )
    all_public_names: list[str] | None = None
    if all_node is not None and isinstance(all_node, (ast.Assign, ast.AnnAssign)):
        value = all_node.value
        if isinstance(value, (ast.List, ast.Tuple)) and all(
            isinstance(element, ast.Constant) and isinstance(element.value, str)
            for element in value.elts
        ):
            all_public_names = [str(element.value) for element in value.elts]
    safe_names: list[str] = []
    blocked: dict[str, list[int]] = {}
    for name, assignment in assignments.items():
        users = loads.get(name, [])
        unsafe = [
            user
            for user in users
            if user not in assignment_nodes and user is not all_node
        ]
        if unsafe:
            blocked[name] = sorted({user.lineno for user in unsafe})
        else:
            safe_names.append(name)

    # Do not remove a producer while a blocked metadata assignment consumes it.
    changed = True
    while changed:
        changed = False
        for name in tuple(safe_names):
            for user in loads.get(name, []):
                user_names = assigned_names(user)
                if any(user_name in blocked for user_name in user_names):
                    safe_names.remove(name)
                    blocked[name] = [user.lineno]
                    changed = True
                    break

    if all_node is not None and all_public_names is None:
        exported_strings = {
            str(node.value)
            for node in ast.walk(all_node)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        for name in tuple(safe_names):
            if name in exported_strings:
                safe_names.remove(name)
                blocked[name] = [all_node.lineno]

    removable_nodes = {
        node
        for node in set(assignments.values())
        if all(name in safe_names for name in assigned_names(node))
    }
    edits: list[tuple[int, int, str]] = []
    for node in removable_nodes:
        start, end = line_span(lines, node)
        edits.append((start, end, ""))

    if all_node is not None and all_public_names is not None:
        filtered = [name for name in all_public_names if name not in safe_names]
        if filtered != all_public_names:
            start, end = line_span(lines, all_node)
            edits.append((start, end, render_all(filtered) + "\n"))

    updated = original
    for start, end, replacement in sorted(edits, reverse=True):
        updated = updated[:start] + replacement + updated[end:]
    record = {
        "path": path.relative_to(ROOT).as_posix(),
        "safe_names": sorted(safe_names),
        "blocked": blocked,
        "status": "WOULD_UPDATE" if edits else "BLOCKED",
    }
    if not apply or not edits:
        return record

    before_module = load_module(path, "before")
    before = public_snapshot(before_module)
    migrated_values = {
        name: json_value(getattr(before_module, name))
        for name in safe_names
    }
    path.write_text(updated, encoding="utf-8", newline="\n")
    try:
        py_compile.compile(str(path), doraise=True)
        after_module = load_module(path, "after")
        after = public_snapshot(after_module)
        if before != after:
            raise AssertionError("public Build inventory changed")
        for name in safe_names:
            if hasattr(after_module, name):
                raise AssertionError(f"removed metadata still exported: {name}")
    except BaseException:
        path.write_bytes(original_bytes)
        raise
    record["status"] = "UPDATED"
    record["removed_lines"] = len(original.splitlines()) - len(updated.splitlines())
    record["migrated_values"] = migrated_values
    return record


def main() -> int:
    """Scan all Builds or apply only statically safe provenance removals."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write safe rewrites")
    parser.add_argument("paths", nargs="*", help="optional Build paths relative to repository root")
    arguments = parser.parse_args()
    paths = [ROOT / value for value in arguments.paths]
    if not paths:
        paths = sorted(BUILD_ROOT.rglob("*-Hardware.py"))
    resolved = [path.resolve() for path in paths]
    originals = {path: path.read_bytes() for path in resolved}
    map_original = PROVENANCE_MAP.read_bytes() if PROVENANCE_MAP.exists() else None
    try:
        records = [rewrite(path, arguments.apply) for path in resolved]
        if arguments.apply:
            if map_original is None:
                provenance = {
                    "schema_version": 1,
                    "kind": "XIANGSHAN_KUNMINGHU_V2_BUILD_PROVENANCE",
                    "entries": {},
                }
            else:
                provenance = json.loads(map_original.decode("utf-8"))
            entries = provenance.setdefault("entries", {})
            for record in records:
                values = record.pop("migrated_values", None)
                if values:
                    existing = entries.setdefault(record["path"], {})
                    if not isinstance(existing, dict):
                        existing = {}
                        entries[record["path"]] = existing
                    existing.update(values)
            provenance["entry_count"] = len(entries)
            provenance["status"] = "AUXILIARY_PROVENANCE_ONLY"
            PROVENANCE_MAP.write_text(
                json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
    except BaseException:
        for path, original in originals.items():
            path.write_bytes(original)
        if map_original is None:
            if PROVENANCE_MAP.exists():
                PROVENANCE_MAP.unlink()
        else:
            PROVENANCE_MAP.write_bytes(map_original)
        raise
    summary = {
        "status": "PASS",
        "apply": arguments.apply,
        "updated": sum(record["status"] == "UPDATED" for record in records),
        "would_update": sum(record["status"] == "WOULD_UPDATE" for record in records),
        "blocked": sum(record["status"] == "BLOCKED" for record in records),
        "records": [
            record
            for record in records
            if record["status"] not in {"NO_ASSIGNMENTS"}
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
