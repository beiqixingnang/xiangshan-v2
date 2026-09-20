"""Rebind strict evidence only when a Build rewrite emits byte-identical RTL."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import types
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "validation"
MIGRATION_EVIDENCE = VALIDATION / "v2-strict-representation-migration-evidence.json"
NEW_MGU = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Backend.Fu.Vector.NewMgu-Hardware.py"
)


def digest(data: bytes) -> str:
    """Return one SHA-256 digest."""

    return hashlib.sha256(data).hexdigest()


def strip_source_attributes(rtl: bytes) -> bytes:
    """Remove only Amaranth source-location attributes from emitted Verilog."""

    text = rtl.decode("utf-8")
    normalized = re.sub(r"\s*\(\* src = \".*?\" \*\)\s*", " ", text)
    return normalized.encode()


def committed_source(revision: str, relative: str) -> bytes:
    """Read one repository file at a fixed Git revision."""

    result = subprocess.run(
        ["git", "show", f"{revision}:{relative}"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return result.stdout


def load_source(source: bytes, path: Path, label: str) -> Any:
    """Execute a Build source snapshot with its canonical path identity."""

    name = f"v2_representation_{label}_{digest(source)[:16]}"
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules[name] = module
    try:
        exec(compile(source, str(path), "exec"), module.__dict__)
    finally:
        sys.modules.pop(name, None)
    return module


def export_variant(module: Any, variant: str) -> str:
    """Export one strict-scope variant through the standard adapter."""

    build = getattr(module, "build_verilog", None)
    if not callable(build):
        raise AttributeError("Build exposes no build_verilog adapter")
    def dependencies() -> dict[str, Any]:
        if variant != "VldMergeUnit":
            return {}
        source = NEW_MGU.read_bytes()
        dependency = load_source(source, NEW_MGU, "new_mgu")
        return {"mask_generator": dependency.NewMgu()}

    attempts = (
        lambda: build({"module": variant}, dependencies()),
        lambda: build(variant, dependencies()),
        lambda: build({}, {}, name=variant),
    )
    failures = []
    for attempt in attempts:
        try:
            rtl = attempt()
            if isinstance(rtl, str) and f"module {variant}" in rtl:
                return rtl
            failures.append("wrong module or non-string result")
        except (KeyError, TypeError, ValueError) as error:
            failures.append(f"{type(error).__name__}: {error}")
    raise RuntimeError(f"cannot export {variant}: {failures}")


def eligible_evidence(path: Path) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Return a complete proof and its Build source record when hash-stale."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("status") != "COMPLETE_EQUIVALENCE":
        return None
    sources = data.get("sources")
    if not isinstance(sources, dict):
        return None
    build = sources.get("python_build")
    if not isinstance(build, dict) or not isinstance(build.get("path"), str):
        return None
    current_path = ROOT / build["path"]
    if not current_path.is_file():
        return None
    current = current_path.read_bytes()
    if build.get("sha256") == digest(current) and build.get("bytes") == len(current):
        return None
    return data, build


def main() -> int:
    """Prove RTL identity for every changed complete proof, then update hashes."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="HEAD", help="Git revision holding evidence-bound Builds")
    arguments = parser.parse_args()
    pending: list[tuple[Path, dict[str, Any], bytes]] = []
    records: list[dict[str, Any]] = []
    for evidence_path in sorted(VALIDATION.glob("*strict-evidence.json")):
        eligible = eligible_evidence(evidence_path)
        if eligible is None:
            continue
        evidence, build_record = eligible
        relative = str(build_record["path"])
        build_path = ROOT / relative
        before_source = committed_source(arguments.baseline, relative)
        after_source = build_path.read_bytes()
        before_hash = digest(before_source)
        after_hash = digest(after_source)
        if before_hash != build_record.get("sha256"):
            raise AssertionError(
                f"{evidence_path.name}: baseline Build hash does not match strict evidence"
            )
        before_module = load_source(before_source, build_path, "before")
        after_module = load_source(after_source, build_path, "after")
        scope = evidence.get("scope", {})
        variants = scope.get("public_variants", []) if isinstance(scope, dict) else []
        if not isinstance(variants, list) or not variants:
            variants = list(getattr(before_module, "COVERED_MODULES", ()))
        if not variants:
            raise AssertionError(f"{evidence_path.name}: complete proof has no public variants")
        variant_records = []
        for value in variants:
            variant = str(value)
            before_rtl = export_variant(before_module, variant).encode()
            after_rtl = export_variant(after_module, variant).encode()
            if before_rtl == after_rtl:
                comparison = "BYTE_IDENTICAL"
                semantic_hash = digest(after_rtl)
            elif strip_source_attributes(before_rtl) == strip_source_attributes(after_rtl):
                comparison = "SOURCE_LOCATION_METADATA_ONLY"
                semantic_hash = digest(strip_source_attributes(after_rtl))
            else:
                raise AssertionError(
                    f"{evidence_path.name}:{variant}: emitted RTL changed"
                )
            variant_records.append(
                {
                    "variant": variant,
                    "rtl_bytes": len(after_rtl),
                    "rtl_sha256": digest(after_rtl),
                    "semantic_rtl_sha256": semantic_hash,
                    "status": comparison,
                }
            )
        updated = json.loads(json.dumps(evidence))
        updated_build = updated["sources"]["python_build"]
        updated_build["sha256"] = after_hash
        updated_build["bytes"] = len(after_source)
        pending.append(
            (
                evidence_path,
                updated,
                evidence_path.read_bytes(),
            )
        )
        records.append(
            {
                "evidence": evidence_path.relative_to(ROOT).as_posix(),
                "build_id": evidence.get("build_id"),
                "build_path": relative,
                "before_build_sha256": before_hash,
                "after_build_sha256": after_hash,
                "before_build_bytes": len(before_source),
                "after_build_bytes": len(after_source),
                "variants": variant_records,
                "status": "RTL_REPRESENTATION_ONLY",
            }
        )

    migration_original = (
        MIGRATION_EVIDENCE.read_bytes() if MIGRATION_EVIDENCE.exists() else None
    )
    try:
        for evidence_path, updated, _original in pending:
            evidence_path.write_text(
                json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        payload = {
            "schema_version": 1,
            "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_REPRESENTATION_MIGRATION",
            "baseline_revision": arguments.baseline,
            "proof_count": len(records),
            "policy": "Evidence hashes are rebound only after every strict-scope public variant emits byte-identical Verilog, or differs solely in Amaranth src file/line attributes whose removal leaves byte-identical Verilog.",
            "records": records,
            "status": "PASS" if records else "NO_CHANGES",
            "strict_count_delta": 0,
        }
        MIGRATION_EVIDENCE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except BaseException:
        for evidence_path, _updated, original in pending:
            evidence_path.write_bytes(original)
        if migration_original is None:
            if MIGRATION_EVIDENCE.exists():
                MIGRATION_EVIDENCE.unlink()
        else:
            MIGRATION_EVIDENCE.write_bytes(migration_original)
        raise
    print(json.dumps({"status": payload["status"], "proofs": len(records)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
