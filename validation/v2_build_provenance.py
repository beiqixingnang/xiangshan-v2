"""Resolve frozen V2 source provenance outside migratable Build modules."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CORE_INVENTORY = ROOT / "V2-Core-Rewrite-Inventory.json"
DEPENDENCY_INVENTORY = ROOT / "V2-Dependency-Family-Inventory.json"
MIGRATED_PROVENANCE = ROOT / "validation/v2-build-provenance-map.json"


def _strings(value: Any) -> tuple[str, ...]:
    """Normalize one inventory field to an ordered string tuple."""

    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item)


@lru_cache(maxsize=1)
def build_source_map() -> dict[str, tuple[str, ...]]:
    """Join the frozen core and dependency inventories by Build path."""

    core = json.loads(CORE_INVENTORY.read_text(encoding="utf-8"))
    dependency = json.loads(DEPENDENCY_INVENTORY.read_text(encoding="utf-8"))
    result: dict[str, tuple[str, ...]] = {}
    for entry in core.get("entries", []):
        if not isinstance(entry, dict):
            continue
        build_path = entry.get("build_path")
        if isinstance(build_path, str) and build_path:
            result[Path(build_path).as_posix()] = _strings(entry.get("source_scala"))
    for family in dependency.get("families", []):
        if not isinstance(family, dict):
            continue
        build_path = family.get("plan_build_file")
        if isinstance(build_path, str) and build_path:
            sources = _strings(family.get("source_paths"))
            if not sources:
                sources = _strings(family.get("source_roots"))
            result[Path(build_path).as_posix()] = sources
    if MIGRATED_PROVENANCE.exists():
        migrated = json.loads(MIGRATED_PROVENANCE.read_text(encoding="utf-8"))
        for build_path, values in migrated.get("entries", {}).items():
            if not isinstance(build_path, str) or not isinstance(values, dict):
                continue
            paths: list[str] = []
            for name, value in values.items():
                if "SOURCE" not in str(name).upper() or "PATH" not in str(name).upper():
                    continue
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            paths.append(item)
                        elif isinstance(item, list):
                            paths.extend(str(child) for child in item if isinstance(child, str))
                elif isinstance(value, dict):
                    for nested in value.values():
                        if isinstance(nested, list):
                            paths.extend(str(item) for item in nested if isinstance(item, str))
            if paths:
                result[Path(build_path).as_posix()] = tuple(dict.fromkeys(paths))
    return result


def relative_build_path(path: str | Path) -> str:
    """Return one repository-relative normalized Build path."""

    candidate = Path(path)
    if candidate.is_absolute():
        candidate = candidate.resolve().relative_to(ROOT.resolve())
    return candidate.as_posix()


def source_paths_for_build(path: str | Path) -> tuple[str, ...]:
    """Return frozen source paths for one Build without importing that Build."""

    relative = relative_build_path(path)
    try:
        return build_source_map()[relative]
    except KeyError as error:
        raise KeyError(f"Build provenance is absent from frozen inventories: {relative}") from error


def provenance_for_build(path: str | Path) -> dict[str, Any]:
    """Return the exact migrated metadata dictionary for one Build."""

    relative = relative_build_path(path)
    if not MIGRATED_PROVENANCE.exists():
        return {}
    migrated = json.loads(MIGRATED_PROVENANCE.read_text(encoding="utf-8"))
    values = migrated.get("entries", {}).get(relative, {})
    return dict(values) if isinstance(values, dict) else {}


__all__ = [
    "build_source_map",
    "provenance_for_build",
    "relative_build_path",
    "source_paths_for_build",
]
