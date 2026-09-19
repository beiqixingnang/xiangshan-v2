"""Rebuild the authoritative strict-equivalence progress rail.

重建严格行为等价验证的权威进度清单。
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "python/Program-System/System-Build/Build-Cpu"
PLAN = ROOT / "V2-Rewrite-Batch-Plan.json"
OUTPUT = ROOT / "validation/v2-strict-equivalence-progress.json"
EXPECTED_KIND = "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE"
NON_COUNTING_STATUSES = ("STRICT_PENDING", "COMPLETE_EQUIVALENCE_VARIANT_ONLY")
LOCKED_REFERENCE_NAMES = {path.stem for path in (ROOT / "validation/reference-sv").glob("*.sv")}
SUCCESS_MARKER = "SAT proof finished - no model found: SUCCESS!"
EQUIV_SUCCESS_MARKERS = (
    "0 are unproven.",
    "Equivalence successfully proven!",
)


def sha256(path: Path) -> str:
    """Return the exact SHA-256 digest. / 返回精确 SHA-256 摘要。"""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def nested(payload: dict[str, Any], *keys: str) -> Any:
    """Read a nested evidence value. / 读取嵌套证据值。"""

    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def status_paths(value: Any, prefix: str = "checks") -> list[tuple[str, str]]:
    """Collect every explicit status below a structured gate tree."""

    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}"
            if key == "status":
                found.append((prefix, str(child)))
            else:
                found.extend(status_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(status_paths(child, f"{prefix}[{index}]"))
    return found


def require_pass_gate(checks: dict[str, Any], name: str,
                      failures: list[str]) -> None:
    """Require a named gate to exist and expose only PASS statuses."""

    if name not in checks:
        failures.append(f"missing required check: {name}")
        return
    statuses = status_paths(checks[name], f"checks.{name}")
    if not statuses:
        failures.append(f"required check has no status: {name}")
        return
    failures.extend(f"gate status {path}: {status}" for path, status in statuses
                    if status != "PASS")


def verify_two_sided_control(control: Any, failures: list[str]) -> None:
    """Require explicit, applied target and reference mutation results."""

    if not isinstance(control, dict) or control.get("status") != "PASS":
        failures.append("missing or failing negative control")
        return
    sides = control.get("sides")
    if not isinstance(sides, dict):
        sides = control.get("cases")
    if not isinstance(sides, dict):
        failures.append("negative control lacks two-sided cases")
        return
    target = [record for name, record in sides.items()
              if str(name).split(".")[-1] == "target"]
    reference = [record for name, record in sides.items()
                 if str(name).split(".")[-1] == "reference"]
    if not target or not reference:
        failures.append("negative control lacks target or reference side")
        return
    for label, records in (("target", target), ("reference", reference)):
        if any(not isinstance(record, dict)
               or record.get("status") != "PASS"
               or record.get("mutation_applied") is not True
               or not any(record.get(marker) is True for marker in (
                   "counterexample_marker", "explicit_failure_marker",
                   "explicit_unproven_cells", "counterexample_detected",
                   "model_found_marker", "counterexample_or_unproven"))
               or not (record.get("success_marker_still_present") is False
                       or record.get("clean_proof_marker_disappeared") is True)
               for record in records):
            failures.append(f"negative control {label} side is not decisive")


def verify_source(record: Any, label: str, failures: list[str]) -> dict[str, Any]:
    """Verify one source path and digest. / 验证一个来源路径及摘要。"""

    if not isinstance(record, dict):
        failures.append(f"missing source record: {label}")
        return {"status": "FAIL"}
    relative = str(record.get("path", ""))
    candidate = Path(relative)
    path = (ROOT / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    try:
        path.relative_to(ROOT.resolve())
        inside_root = True
    except ValueError:
        inside_root = False
        failures.append(f"source outside repository: {label}")
    expected = str(record.get("sha256", ""))
    present = path.is_file()
    observed = sha256(path) if present else None
    matched = inside_root and present and bool(expected) and observed == expected
    if not matched:
        failures.append(f"source digest: {label}")
    return {
        "path": relative,
        "present": present,
        "inside_repository": inside_root,
        "expected_sha256": expected,
        "observed_sha256": observed,
        "status": "PASS" if matched else "FAIL",
    }


def locked_reference_names() -> set[str]:
    """Return every module name that has an exact locked reference file."""

    return {path.stem for path in (ROOT / "validation/reference-sv").glob("*.sv")}


def _static_value(node: ast.AST, values: dict[str, Any]) -> Any:
    """Resolve the small constant-expression subset used by Build catalogs."""

    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        items = [_static_value(item, values) for item in node.elts]
        return items if all(item is not None for item in items) else None
    if isinstance(node, ast.Dict):
        if any(key is None for key in node.keys):
            return None
        keys = [_static_value(key, values) for key in node.keys if key is not None]
        entries = [_static_value(value, values) for value in node.values]
        if all(key is not None for key in keys) and all(value is not None for value in entries):
            return dict(zip(keys, entries, strict=True))
        return None
    if isinstance(node, ast.Name):
        return values.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_value(node.left, values)
        right = _static_value(node.right, values)
        if isinstance(left, list) and isinstance(right, list):
            return left + right
        return None
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in {"list", "set", "sorted", "tuple"}
            and len(node.args) == 1 and not node.keywords):
        value = _static_value(node.args[0], values)
        if isinstance(value, dict):
            return list(value)
        if isinstance(value, (list, tuple, set)):
            return list(value)
    return None


def _string_members(value: Any) -> set[str]:
    """Return string members from a resolved catalog sequence or mapping."""

    if isinstance(value, dict):
        return {str(item) for item in value if isinstance(item, str)}
    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value if isinstance(item, str)}
    return set()


def _runtime_catalog_members(build_path: Path, failures: list[str]) -> list[str]:
    """Import one side-effect-free Build and read its public catalog."""

    module_name = f"_v2_progress_catalog_{hashlib.sha256(str(build_path).encode()).hexdigest()[:16]}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, build_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot create import spec for {build_path.name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(module_name, None)
    except Exception as error:  # The audit must record import failures, not crash.
        failures.append(f"runtime Build catalog import failed: {type(error).__name__}: {error}")
        return []
    for attribute in ("LOCKED_VARIANTS", "COVERED_MODULES"):
        value = getattr(module, attribute, None)
        if value is None:
            continue
        if not isinstance(value, (list, tuple)) or not value \
                or not all(isinstance(item, str) and item for item in value):
            failures.append(f"runtime Build catalog {attribute} is not a non-empty string sequence")
            return []
        members = list(value)
        if len(members) != len(set(members)):
            failures.append(f"runtime Build catalog {attribute} repeats a member")
        return sorted(members)
    return []


def build_declared_members(build_path: Path, failures: list[str] | None = None) -> list[str]:
    """Enumerate every module name a catalog Build declares.

    Covers ``COVERED_MODULES`` and ``*_MEMBERS`` tuples plus ``*_SPECS`` mapping
    keys and string-compared member selectors, keeping only names that have an
    exact locked reference file. Reference availability is checked separately;
    silently filtering a missing reference would turn a partial proof into a
    complete one.
    """

    catalog_failures = failures if failures is not None else []
    if not build_path.is_file():
        return []
    text = build_path.read_text(encoding="utf-8")
    values: dict[str, Any] = {}
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = ast.Module(body=[], type_ignores=[])
    for statement in tree.body:
        name: str | None = None
        value_node: ast.AST | None = None
        if (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)):
            name = statement.targets[0].id
            value_node = statement.value
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            name = statement.target.id
            value_node = statement.value
        if name is not None and value_node is not None:
            resolved = _static_value(value_node, values)
            if resolved is not None:
                values[name] = resolved
    static_primary: set[str] = set()
    for primary in ("LOCKED_VARIANTS", "COVERED_MODULES"):
        members = _string_members(values.get(primary))
        if members:
            static_primary = members
            break
    candidates: set[str] = set()
    for name, value in values.items():
        if name.endswith("_MEMBERS") or name.endswith("_SPECS"):
            candidates |= _string_members(value)
    for table in re.finditer(r'\b(?:COVERED_MODULES|[A-Z_]+_MEMBERS)[^=]*=\s*([\(\[])(.*?)[\)\]]',
                             text, re.S):
        candidates |= set(re.findall(r'"([^"]+)"', table.group(2)))
    for spec_name in re.findall(r'^([A-Z_]+_SPECS):', text, re.M):
        block = re.search(re.escape(spec_name) + r':.*?\n\}', text, re.S)
        if block is not None:
            candidates |= set(re.findall(r'^\s{4}"([^"]+)":', block.group(0), re.M))
    candidates |= set(re.findall(
        r'(?:member|module_name|subject|module)\s*==\s*"([A-Za-z_]\w*)"', text))
    runtime_members = _runtime_catalog_members(build_path, catalog_failures)
    if runtime_members:
        if static_primary and set(runtime_members) != static_primary:
            catalog_failures.append(
                "runtime/static Build catalog mismatch: "
                f"runtime={len(runtime_members)}, static={len(static_primary)}"
            )
        return runtime_members
    return sorted(static_primary or candidates)


def build_declared_scala_paths(build_path: Path) -> set[str]:
    """Return repository-relative Scala paths named by a Build contract."""

    if not build_path.is_file():
        return set()
    return set(re.findall(
        r'["\'](upstream/[^"\']+\.scala)["\']',
        build_path.read_text(encoding="utf-8")))


def verify_record_map(records: Any, label: str, failures: list[str]) -> dict[str, Any]:
    """Verify every path/digest entry in a named evidence mapping."""

    if not isinstance(records, dict):
        return {}
    return {str(name): verify_source(record, f"{label}.{name}", failures)
            for name, record in records.items() if isinstance(record, dict) and "path" in record}


def verify_reference_lock(payload: dict[str, Any], failures: list[str]) -> dict[str, Any]:
    """Re-hash every per-module reference claimed by aggregate evidence."""

    lock = payload.get("reference_lock", {})
    if not isinstance(lock, dict):
        return {}
    hashes = lock.get("sha256_by_module", {})
    result: dict[str, Any] = {}
    locked_reference = lock.get("locked_reference")
    if isinstance(locked_reference, dict) and "path" in locked_reference:
        result["locked_reference"] = verify_source(
            locked_reference, "reference_lock.locked_reference", failures)
    elif isinstance(locked_reference, str) and lock.get("locked_reference_sha256"):
        result["locked_reference"] = verify_source(
            {"path": locked_reference, "sha256": lock.get("locked_reference_sha256")},
            "reference_lock.locked_reference", failures)
    elif isinstance(lock.get("path"), str) and str(lock.get("path")).endswith(".sv") and lock.get("sha256"):
        result["locked_reference"] = verify_source(
            {"path": lock.get("path"), "sha256": lock.get("sha256")},
            "reference_lock.locked_reference", failures)
    if isinstance(hashes, dict):
        for module, expected in hashes.items():
            record = {"path": f"validation/reference-sv/{module}.sv", "sha256": expected}
            result[str(module)] = verify_source(record, f"reference_lock.{module}", failures)
    children = lock.get("child_references", {})
    result.update(verify_record_map(children, "reference_lock.child", failures))
    return result


def verify_declared_scala(payload: dict[str, Any], failures: list[str], counted: bool) -> dict[str, Any]:
    """Require every declared Scala dependency of a counted Build to be vendored."""

    sources = payload.get("sources", {})
    declared = sources.get("declared_scala_sources", {}) if isinstance(sources, dict) else {}
    result: dict[str, Any] = {}
    if not isinstance(declared, dict):
        return result
    for name, record in declared.items():
        if not isinstance(record, dict):
            failures.append(f"invalid declared Scala record: {name}")
            continue
        if record.get("vendored") is not True:
            result[str(name)] = {"status": "MISSING", "note": record.get("note")}
            if counted:
                failures.append(f"declared Scala source not vendored: {name}")
            continue
        path = str(name)
        digest = record.get("sha256")
        result[path] = verify_source({"path": path, "sha256": digest},
                                     f"declared_scala.{name}", failures)
    dependencies = sources.get("scala_dependencies", {}) if isinstance(sources, dict) else {}
    result.update(verify_record_map(dependencies, "scala_dependency", failures))
    return result


def verify_variant_scope(payload: dict[str, Any], failures: list[str], counted: bool) -> dict[str, Any]:
    """Validate every aggregate member rather than trusting only its aggregate marker."""

    scope = payload.get("scope", {})
    if not isinstance(scope, dict):
        return {}
    public = scope.get("public_variants")
    variants = scope.get("variants")
    strict_variant_audit = counted and bool(nested(payload, "audit_policy", "scope_source"))
    if not isinstance(public, list):
        return {}
    if not isinstance(variants, dict):
        if strict_variant_audit and len(public) > 1:
            failures.append("aggregate public_variants missing per-variant records")
        return {}
    public_names = {str(item) for item in public}
    detailed_variants = nested(payload, "checks", "variants")
    detailed_by_name: dict[str, Any] = {}
    if isinstance(detailed_variants, list) and len(detailed_variants) == len(public):
        detailed_by_name = {
            str(name): record
            for name, record in zip(public, detailed_variants, strict=True)
            if isinstance(record, dict)
        }
    if strict_variant_audit and public_names != set(variants):
        failures.append("public_variants and variant records differ")
    if strict_variant_audit and scope.get("variant_count") not in (None, len(public_names)):
        failures.append("variant_count mismatch")
    checked: dict[str, Any] = {}
    for name, raw in variants.items():
        member_failures: list[str] = []
        if not isinstance(raw, dict):
            member_failures.append("not an object")
            raw = {}
        inputs = raw.get("inputs", {})
        outputs = raw.get("outputs_compared", {})
        if not isinstance(inputs, dict) or not inputs:
            member_failures.append("missing inputs")
        if not isinstance(outputs, dict) or not outputs:
            member_failures.append("missing outputs")
        if raw.get("input_bits") not in (None, sum(int(v) for v in inputs.values())):
            member_failures.append("input bit count")
        if raw.get("output_bits") not in (None, sum(int(v) for v in outputs.values())):
            member_failures.append("output bit count")
        reference = raw.get("locked_reference")
        digest = raw.get("locked_sha256")
        if reference or digest:
            local_failures: list[str] = []
            verify_source({"path": reference, "sha256": digest},
                          f"variant.{name}.reference", local_failures)
            member_failures.extend(local_failures)
        if raw.get("abi_exact") is not True:
            member_failures.append("ABI")
        if raw.get("deterministic") is not True:
            member_failures.append("deterministic export")
        if raw.get("miter_selfcheck") is not True:
            member_failures.append("miter selfcheck")
        if "view_trusted" in raw and raw.get("view_trusted") is not True:
            member_failures.append("reference view")
        if nested(payload, "audit_policy", "require_locked_reference_lint") is True \
                and raw.get("locked_reference_lint") != "PASS":
            member_failures.append("locked reference lint")
        sat = raw.get("sat")
        if isinstance(sat, dict):
            if sat.get("returncode") != 0 or sat.get("status") != "PASS":
                member_failures.append("SAT status")
            if sat.get("formal_success_marker") is not True or sat.get("unconstrained") is not True:
                member_failures.append("SAT completeness")
        elif "method" in raw:
            if raw.get("verdict") != "PASS" or raw.get("success_marker") is not True:
                member_failures.append("formal verdict")
            if raw.get("sequential"):
                cells = raw.get("unconstrained_or_cells", raw.get("unconstrained_or_equiv_cells"))
                if not isinstance(cells, int) or isinstance(cells, bool) or cells <= 0:
                    member_failures.append("zero/missing equivalence cells")
                proven = raw.get("proven_cells")
                if not isinstance(proven, int) or isinstance(proven, bool) or proven != cells:
                    member_failures.append("incomplete proven equivalence cells")
                if raw.get("unproven_cells") != 0:
                    member_failures.append("unproven equivalence cells")
                markers = raw.get("markers_present")
                if not isinstance(markers, dict):
                    detail = detailed_by_name.get(str(name), {})
                    markers = detail.get("yosys_equiv", {}).get("markers_present") \
                        if isinstance(detail, dict) else None
                if not isinstance(markers, dict) or not all(
                        markers.get(marker) is True for marker in EQUIV_SUCCESS_MARKERS):
                    member_failures.append("sequential equivalence full-output markers")
            else:
                free = raw.get("unconstrained_or_cells", raw.get("unconstrained_or_equiv_cells"))
                if free is not True:
                    member_failures.append("constrained SAT")
        if member_failures and strict_variant_audit:
            failures.extend(f"variant {name}: {item}" for item in member_failures)
        checked[str(name)] = {"status": "PASS" if not member_failures else "FAIL",
                              "failures": member_failures}
    require_control = bool(nested(payload, "audit_policy", "require_negative_control"))
    if strict_variant_audit and len(public_names) > 1 and require_control:
        control = nested(payload, "checks", "negative_control")
        if not isinstance(control, dict) or control.get("status") != "PASS":
            failures.append("aggregate negative control")
    return checked


def verify_evidence(path: Path, expected_source_commit: str) -> dict[str, Any]:
    """Verify one strict proof without trusting its status string alone. / 不仅依赖状态字符串，验证一份严格证明。"""

    payload = json.loads(path.read_text(encoding="utf-8"))
    failures: list[str] = []
    build_id = str(payload.get("build_id", ""))
    audit_policy = payload.get("audit_policy")
    hardened = isinstance(audit_policy, dict)
    if payload.get("kind") != EXPECTED_KIND:
        failures.append("kind")
    declared_status = str(payload.get("status", ""))
    non_counting = declared_status in NON_COUNTING_STATUSES
    if non_counting:
        if payload.get("strict_complete_eligible") is not False:
            failures.append("non-counting record must not claim strict_complete_eligible")
        if payload.get("strict_complete_count_delta") != 0:
            failures.append("non-counting record must claim strict_complete_count_delta 0")
    else:
        if declared_status != "COMPLETE_EQUIVALENCE":
            failures.append("status")
        if payload.get("strict_complete_eligible") is not True:
            failures.append("strict_complete_eligible")
        if payload.get("strict_complete_count_delta") != 1:
            failures.append("strict_complete_count_delta")
    if not build_id:
        failures.append("build_id")
    validator_path = str(payload.get("validator", ""))
    if not non_counting and not hardened:
        failures.append("counted evidence missing audit_policy")
    validator = (ROOT / validator_path).resolve()
    try:
        validator.relative_to(ROOT.resolve())
        validator_inside = True
    except ValueError:
        validator_inside = False
    if not validator_inside or not validator.is_file():
        failures.append("validator path")
    source_commit = str(payload.get("source_commit", ""))
    if source_commit != expected_source_commit:
        failures.append("source_commit")

    sources = payload.get("sources", {})
    verified_sources = {
        name: verify_source(record, name, failures)
        for name, record in sources.items()
        if name in {"validator", "python_build", "scala", "reference_sv"}
    } if isinstance(sources, dict) else {}
    if nested(payload, "audit_policy", "require_validator_hash") is True:
        if "validator" not in verified_sources:
            failures.append("required source: validator")
        elif str(verified_sources["validator"].get("path", "")) != validator_path:
            failures.append("validator source path does not match validator field")
    for required in ("python_build", "reference_sv"):
        if required not in verified_sources:
            failures.append(f"required source: {required}")
    if non_counting:
        if "scala" not in verified_sources:
            row_note = "scala provenance not vendored for this attempt record"
        else:
            row_note = None
    elif "scala" not in verified_sources:
        failures.append("required source: scala")
        row_note = None
    else:
        row_note = None
    source_children = verify_record_map(
        sources.get("reference_children", {}) if isinstance(sources, dict) else {},
        "reference_child", failures)
    reference_lock = verify_reference_lock(payload, failures)
    declared_scala = verify_declared_scala(payload, failures, counted=not non_counting)
    variant_checks = verify_variant_scope(payload, failures, counted=not non_counting)
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        checks = {}
        if not non_counting:
            failures.append("checks object")
    scope_for_gates = payload.get("scope", {})
    public_for_gates = scope_for_gates.get("public_variants", []) \
        if isinstance(scope_for_gates, dict) else []
    variants_for_gates = scope_for_gates.get("variants", {}) \
        if isinstance(scope_for_gates, dict) else {}
    all_sequential_variants = (
        isinstance(public_for_gates, list)
        and len(public_for_gates) > 1
        and isinstance(variants_for_gates, dict)
        and set(str(item) for item in public_for_gates) == set(variants_for_gates)
        and all(isinstance(record, dict)
                and record.get("sequential") is True
                and record.get("method") == "sequential_equivalence"
                for record in variants_for_gates.values())
    )
    if not non_counting:
        declared_failures = payload.get("failures")
        declared_unclosed = payload.get("unclosed")
        if declared_failures != []:
            failures.append("counted evidence declares failures")
        if declared_unclosed != []:
            failures.append("counted evidence declares unclosed strict work")
        require_pass_gate(checks, "py_compile", failures)
        require_pass_gate(checks, "pyright", failures)
        for status_path, status in status_paths(checks):
            allowed_not_applicable = all_sequential_variants and status == "NOT_APPLICABLE" \
                and status_path in {
                    "checks.formal.yosys_formal_miter",
                    "checks.aggregate_sat_miter",
                }
            if status != "PASS" and not allowed_not_applicable:
                failures.append(f"gate status {status_path}: {status}")
        public = payload.get("scope", {}).get("public_variants", [])
        if not isinstance(public, list) or len(public) <= 1:
            require_pass_gate(checks, "abi", failures)
            require_pass_gate(checks, "deterministic_export", failures)
    if not non_counting:
        if nested(payload, "audit_policy", "require_negative_control") is not True:
            failures.append("audit_policy does not require negative control")
        control = nested(payload, "checks", "negative_control")
        if not isinstance(control, dict):
            control = nested(payload, "checks", "formal", "negative_control")
        verify_two_sided_control(control, failures)

    claimed_variants: set[str] = set()
    if isinstance(scope_claim := payload.get("scope"), dict):
        if isinstance(public_variants := scope_claim.get("public_variants"), list):
            claimed_variants |= {str(item) for item in public_variants}
        if isinstance(variant_map := scope_claim.get("variants"), dict):
            claimed_variants |= {str(item) for item in variant_map}
    claimed_build = str(verified_sources.get("python_build", {}).get("path", ""))
    if hardened and claimed_build:
        expected_build_id = re.sub(r"-Hardware\.py$", "", Path(claimed_build).name)
        if build_id != expected_build_id:
            failures.append("build_id does not match python Build filename")
    if not non_counting and claimed_build:
        declared_paths = build_declared_scala_paths(ROOT / claimed_build)
        recorded_scala = {
            str(verified_sources.get("scala", {}).get("path", "")),
            *(str(record.get("path", "")) for record in declared_scala.values()
              if isinstance(record, dict)),
        }
        missing_scala = sorted(declared_paths - recorded_scala)
        if missing_scala:
            failures.append(
                "Build-declared Scala sources are not locked in evidence: "
                + ", ".join(missing_scala))
        member_list = build_declared_members(ROOT / claimed_build, failures)
        members = set(member_list)
        if len(member_list) != len(members):
            failures.append("aggregate Build declares duplicate locked members")
        missing_references = sorted(members - LOCKED_REFERENCE_NAMES)
        if missing_references:
            failures.append(
                "aggregate Build members lack locked references: "
                + ", ".join(missing_references)
            )
        if len(members) > 1 and not members <= claimed_variants:
            failures.append(
                f"aggregate Build exposes {len(members)} locked members but only "
                f"{len(members & claimed_variants)} are proven here")

    if not non_counting and claimed_variants:
        locked_reference_names_for_record = {
            str(name) for name in reference_lock
            if name != "locked_reference"
        }
        locked_reference_names_for_record |= set(source_children)
        top_reference = str(verified_sources.get("reference_sv", {}).get("path", ""))
        if top_reference:
            locked_reference_names_for_record.add(Path(top_reference).stem)
        for name, raw in (payload.get("scope", {}).get("variants", {}) or {}).items():
            if isinstance(raw, dict) and raw.get("locked_reference") and raw.get("locked_sha256"):
                locked_reference_names_for_record.add(str(name))
        missing_variant_refs = sorted(claimed_variants - locked_reference_names_for_record)
        if missing_variant_refs:
            failures.append(
                "aggregate variants lack verified locked references: "
                + ", ".join(missing_variant_refs))

    proof_method = "sequential_variant_set" if all_sequential_variants else "sat_miter"
    formal = {} if all_sequential_variants else nested(
        payload, "checks", "formal", "yosys_formal_miter")
    if not all_sequential_variants and not isinstance(formal, dict):
        proof_method = "sequential_equivalence"
        formal = nested(payload, "checks", "formal", "yosys_equiv")
    if not all_sequential_variants and not isinstance(formal, dict):
        formal = {}
        if not non_counting:
            failures.append("formal result")
    formal_command = formal.get("command", [])
    command_text = " ".join(str(item) for item in formal_command) if isinstance(formal_command, list) else str(formal_command)
    if not non_counting and not all_sequential_variants:
        if formal.get("returncode") != 0 or formal.get("status") != "PASS":
            failures.append("formal status")
        if formal.get("formal_success_marker") is not True:
            failures.append("formal_success_marker")
        if proof_method == "sat_miter":
            if "yosys" not in command_text or "sat -prove mismatch 0" not in command_text:
                failures.append("SAT proof command")
            full_success = any(formal.get(key) is True for key in (
                "sat_success_marker", "success_marker", "success_marker_in_full_output"))
            if not full_success:
                failures.append("SAT full-output success marker")
            full_unconstrained = any(formal.get(key) is True for key in (
                "unconstrained", "unconstrained_marker", "free_input_marker_in_full_output"))
            if not full_unconstrained:
                failures.append("SAT proof has assumptions or lacks full-output free-input marker")
        else:
            if "equiv_induct" not in command_text or "equiv_status -assert" not in command_text:
                failures.append("sequential equivalence command")
            markers = formal.get("markers_present")
            if not isinstance(markers, dict) or not all(
                    markers.get(marker) is True for marker in EQUIV_SUCCESS_MARKERS):
                failures.append("sequential equivalence full-output markers")
            proven = formal.get("proven_cells")
            unproven = formal.get("unproven_cells")
            equiv_cells = formal.get("equiv_cells")
            if (not isinstance(proven, int) or isinstance(proven, bool)
                    or not isinstance(unproven, int) or isinstance(unproven, bool)
                    or not isinstance(equiv_cells, int) or isinstance(equiv_cells, bool)):
                failures.append("sequential equivalence cell summary")
            elif proven <= 0 or equiv_cells <= 0 or unproven != 0 or proven != equiv_cells:
                failures.append("sequential equivalence cells not completely proven")

        public = payload.get("scope", {}).get("public_variants", [])
        variants = payload.get("scope", {}).get("variants", {})
        if isinstance(public, list) and len(public) > 1 and isinstance(variants, dict):
            combinational = sum(
                not bool(record.get("sequential"))
                for record in variants.values() if isinstance(record, dict) and "method" in record)
            expected_mitered = combinational if combinational else len(public)
            observed_mitered = formal.get("mitered_variants")
            if observed_mitered != expected_mitered:
                failures.append(
                    f"aggregate miter covers {observed_mitered}, expected {expected_mitered}")

    scope = payload.get("scope", {})
    if not isinstance(scope, dict) or not scope.get("inputs") or not scope.get("outputs_compared"):
        if not non_counting:
            failures.append("formal scope")
    return {
        "evidence": str(path.relative_to(ROOT)).replace("\\", "/"),
        "build_id": build_id,
        "declared_status": declared_status,
        "source_commit": {
            "expected": expected_source_commit,
            "observed": source_commit,
            "status": "PASS" if source_commit == expected_source_commit else "FAIL",
        },
        "status": ("NON_COUNTING" if non_counting and not failures
                   else "PASS" if not failures else "FAIL"),
        "note": row_note,
        "scope": scope,
        "sources": verified_sources,
        "source_children": source_children,
        "reference_lock": reference_lock,
        "declared_scala_sources": declared_scala,
        "variant_checks": variant_checks,
        "formal": {
            "proof_method": proof_method,
            "command": formal.get("command"),
            "returncode": formal.get("returncode"),
            "status": formal.get("status"),
            "formal_success_marker": formal.get("formal_success_marker"),
        },
        "failures": failures,
        "declared_failures": payload.get("failures", []),
        "declared_unclosed": payload.get("unclosed", []),
    }


def main() -> int:
    """Reconcile strict proofs against the dynamic Build denominator. / 根据动态 Build 分母核对严格证明。"""

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    scan_freeze = plan.get("scan_freeze", {})
    expected_source_commit = str(scan_freeze.get("source_commit", ""))
    evidence_paths = sorted((ROOT / "validation").glob("v2-*-strict-evidence.json"))
    rows = [verify_evidence(path, expected_source_commit) for path in evidence_paths]
    seen: set[str] = set()
    duplicates: list[str] = []
    for row in rows:
        build_id = str(row["build_id"])
        if build_id in seen:
            duplicates.append(build_id)
            row["status"] = "FAIL"
            row["failures"].append("duplicate build_id")
        seen.add(build_id)
    builds = sorted(BUILD_ROOT.rglob("*.py"))
    build_claims: dict[str, list[str]] = {}
    for row in rows:
        if row["status"] != "PASS":
            continue
        claimed_path = str(row["sources"].get("python_build", {}).get("path", ""))
        if claimed_path:
            build_claims.setdefault(claimed_path, []).append(str(row["build_id"]))
    aggregate_claims = {path: ids for path, ids in build_claims.items() if len(ids) > 1}
    for row in rows:
        row_path = str(row["sources"].get("python_build", {}).get("path", ""))
        if row["status"] == "PASS" and row_path in aggregate_claims:
            row["status"] = "FAIL"
            row["failures"].append(
                "aggregate Build claimed by "
                f"{len(aggregate_claims[row_path])} strict proofs: {row_path}"
            )
    strict_count = sum(row["status"] == "PASS" for row in rows)
    denominator = len(builds)
    execution = plan.get("execution_state", {})
    plan_count = execution.get("strict_complete_equivalence_build_count")
    plan_denominator = execution.get("strict_complete_equivalence_build_denominator")
    reconciliation = (
        "PASS" if plan_count == strict_count and plan_denominator == denominator else "FAIL"
    )
    accepted_rows = [row for row in rows if row["status"] in ("PASS", "NON_COUNTING")]
    non_counting = [{"evidence": row["evidence"], "build_id": row["build_id"],
                     "declared_status": row["declared_status"],
                     "audit_failures": row["failures"],
                     "proof_failures": row["declared_failures"],
                     "unclosed": row["declared_unclosed"]}
                    for row in rows if row["status"] == "NON_COUNTING"]
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_EQUIVALENCE_PROGRESS",
        "build_denominator": denominator,
        "strict_complete_build_count": strict_count,
        "fraction": f"{strict_count}/{denominator}",
        "percentage": round(100.0 * strict_count / denominator, 6) if denominator else 0.0,
        "policy": "Only independently reverified COMPLETE_EQUIVALENCE evidence with the locked source commit, matching source hashes, and either a Yosys SAT no-model miter or fully proven Yosys inductive-equivalence status is counted. STRICT_PENDING and COMPLETE_EQUIVALENCE_VARIANT_ONLY records are inventoried as attempted-but-not-counted instead of failing the rail, and one Build file may not be claimed by several counting proofs.",
        "non_counting_attempt_count": len(non_counting),
        "non_counting_attempts": non_counting,
        "plan_reconciliation": {
            "plan_count": plan_count,
            "plan_denominator": plan_denominator,
            "status": reconciliation,
        },
        "duplicate_build_ids": duplicates,
        "aggregate_build_claim_conflicts": {
            path: ids for path, ids in sorted(aggregate_claims.items())
        },
        "proofs": rows,
        "status": "PASS" if len(accepted_rows) == len(rows) and reconciliation == "PASS" else "FAIL",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "fraction": payload["fraction"],
                      "proofs": strict_count, "non_counting": len(non_counting),
                      "duplicates": duplicates}, ensure_ascii=False))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
