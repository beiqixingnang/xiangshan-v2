"""Rebuild the authoritative strict-equivalence progress rail.

重建严格行为等价验证的权威进度清单。
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "python/Program-System/System-Build/Build-Cpu"
PLAN = ROOT / "V2-Rewrite-Batch-Plan.json"
OUTPUT = ROOT / "validation/v2-strict-equivalence-progress.json"
RELOCATION_BASELINE = "8ddf8d6609e653e313d6d8924f16335a973bc80a"
EXPECTED_KIND = "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE"
NON_COUNTING_STATUSES = ("STRICT_PENDING", "COMPLETE_EQUIVALENCE_VARIANT_ONLY")
LOCKED_REFERENCE_NAMES = {path.stem for path in (ROOT / "validation/reference-sv").glob("*.sv")}
SUCCESS_MARKER = "SAT proof finished - no model found: SUCCESS!"
EQUIV_SUCCESS_MARKERS = (
    "0 are unproven.",
    "Equivalence successfully proven!",
)
STOREQUEUE_BUILD_ID = "Build-Cpu.Memory.Lsqueue.StoreQueueData"
STOREQUEUE_BUILD_PATH = (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/"
    "Cpu-Memory-Memory.Lsqueue.StoreQueueData-Hardware.py"
)
STOREQUEUE_VALIDATOR_PATH = "validation/v2_storequeue_strict_validator.py"
STOREQUEUE_COMPOSITION_VALIDATOR_PATH = "validation/v2_storequeue_composition_validator.py"
STOREQUEUE_RAIL_PATH = "validation/v2_strict_family_rail.py"
STOREQUEUE_PROFILE = "storequeue_child_theorem_parent_glue_v1"
STOREQUEUE_COMPOSED_METHOD = "compositional_sequential_equivalence"
STOREQUEUE_GLUE_METHOD = "compositional_unrestricted_sat"
STOREQUEUE_MEMBERS = (
    "SQAddrModule", "SQAddrModule_1", "SQData8Module", "SQDataModule",
)
STOREQUEUE_LEAF_MEMBERS = STOREQUEUE_MEMBERS[:3]
STOREQUEUE_LANES = tuple(range(16))
STOREQUEUE_ARTIFACTS = (
    "dut_parent_export", "reference_parent_view",
    "dut_child_export", "reference_child_view",
    "base_glue_miter", "target_input_slice_mutation_miter",
    "reference_mask_bit_mutation_miter",
)
STOREQUEUE_NEGATIVE_CONTROLS = {
    "target_input_slice_mutation": {
        "side": "dut", "lane": 0, "port": "io_data_wdata_0",
        "expression": "io_data_wdata_0[15:8]",
        "miter": "target_input_slice_mutation_miter",
    },
    "reference_mask_bit_mutation": {
        "side": "reference", "lane": 0, "port": "io_mask_wdata_0",
        "expression": "io_mask_wdata_0[1]",
        "miter": "reference_mask_bit_mutation_miter",
    },
}


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


def valid_sha256(value: Any) -> bool:
    """Return whether a value is a lowercase SHA-256 digest."""

    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _load_module(path: Path, name: str) -> Any:
    """Import one exact, already hash-checked Python source path."""

    validation_dir = str(ROOT / "validation")
    if validation_dir not in sys.path:
        sys.path.insert(0, validation_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def render_storequeue_composition_artifacts(build_path: Path) -> dict[str, str]:
    """Re-export and rebuild the three StoreQueue glue miters in memory.

    This performs deterministic Python/Amaranth export and string rendering only;
    it does not write files or invoke Yosys. Rebuilding the proof inputs lets the
    central rail compare the recorded hashes to the current Build and locked refs
    even after ignored ``validation/.work`` artifacts have disappeared.
    """

    validator = _load_module(
        ROOT / STOREQUEUE_COMPOSITION_VALIDATOR_PATH,
        "_v2_progress_storequeue_renderer")
    build = validator.load_build(build_path)

    def exported(member: str, dut_name: str) -> str:
        raw = build.build_verilog({"module": member}, {})
        if not isinstance(raw, str):
            raise TypeError(f"Build export for {member} is not text")
        return validator.rename_top_module(raw, member, dut_name)

    dut_parent = exported("SQDataModule", "DUT_SQDataModule")
    dut_child = exported("SQData8Module", "DUT_SQData8Module")
    ref_parent = validator.rename_top_module(
        (ROOT / "validation/reference-sv/SQDataModule.sv").read_text(encoding="utf-8"),
        "SQDataModule", "REF_SQDataModule")
    ref_child = validator.rename_top_module(
        (ROOT / "validation/reference-sv/SQData8Module.sv").read_text(encoding="utf-8"),
        "SQData8Module", "REF_SQData8Module")
    return {
        "dut_parent_export": dut_parent,
        "reference_parent_view": ref_parent,
        "dut_child_export": dut_child,
        "reference_child_view": ref_child,
        "base_glue_miter": validator.build_parent_glue_miter(
            dut_parent, ref_parent, dut_child, ref_child),
        "target_input_slice_mutation_miter": validator.build_parent_glue_miter(
            dut_parent, ref_parent, dut_child, ref_child,
            ("dut", 0, "io_data_wdata_0", "io_data_wdata_0[15:8]")),
        "reference_mask_bit_mutation_miter": validator.build_parent_glue_miter(
            dut_parent, ref_parent, dut_child, ref_child,
            ("reference", 0, "io_mask_wdata_0", "io_mask_wdata_0[1]")),
    }


def _check_source_binding(binding: Any, verified: Any, label: str,
                          failures: list[str], expected_path: str | None = None) -> None:
    """Require a duplicated binding to match an independently rehashed source."""

    if not isinstance(binding, dict) or not isinstance(verified, dict):
        failures.append(f"StoreQueue source binding missing: {label}")
        return
    if verified.get("status") != "PASS":
        failures.append(f"StoreQueue bound source is not current: {label}")
    if binding.get("path") != verified.get("path"):
        failures.append(f"StoreQueue source binding path: {label}")
    if binding.get("sha256") != verified.get("observed_sha256"):
        failures.append(f"StoreQueue source binding digest: {label}")
    size = binding.get("bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        failures.append(f"StoreQueue source binding byte count: {label}")
    else:
        source_path = ROOT / str(binding.get("path", ""))
        if not source_path.is_file() or source_path.stat().st_size != size:
            failures.append(f"StoreQueue source binding current size: {label}")
    if expected_path is not None and binding.get("path") != expected_path:
        failures.append(f"StoreQueue source binding identity: {label}")


def _check_storequeue_formal_receipt(receipt: Any, label: str,
                                     failures: list[str], *, sat: bool,
                                     expected_miter_sha256: str | None = None) -> None:
    """Check a StoreQueue proof receipt without trusting its status field alone."""

    if not isinstance(receipt, dict):
        failures.append(f"StoreQueue formal receipt missing: {label}")
        return
    if receipt.get("status") != "PASS":
        failures.append(f"StoreQueue formal status: {label}")
    returncode = receipt.get("returncode")
    if not isinstance(returncode, int) or isinstance(returncode, bool):
        failures.append(f"StoreQueue formal returncode: {label}")
    if receipt.get("timed_out") is not False:
        failures.append(f"StoreQueue formal timeout: {label}")
    if not isinstance(receipt.get("command"), (list, str)):
        failures.append(f"StoreQueue formal command missing: {label}")
    command = receipt.get("command", [])
    command_text = " ".join(str(item) for item in command) if isinstance(command, list) else str(command)
    if "yosys" not in command_text:
        failures.append(f"StoreQueue formal command is not Yosys: {label}")
    if sat and "sat -prove mismatch 0" not in command_text:
        failures.append(f"StoreQueue glue SAT command: {label}")
    output_hash = receipt.get("output_sha256")
    if not valid_sha256(output_hash):
        failures.append(f"StoreQueue full-output digest: {label}")
    output_tail = receipt.get("output_tail")
    if not isinstance(output_tail, str) or not output_tail:
        failures.append(f"StoreQueue formal output tail missing: {label}")
    if sat:
        if returncode != 0:
            failures.append(f"StoreQueue SAT proof returncode: {label}")
        if receipt.get("formal_success_marker") is not True:
            failures.append(f"StoreQueue SAT success marker: {label}")
        if not any(receipt.get(key) is True for key in (
                "sat_success_marker", "success_marker", "success_marker_in_full_output")):
            failures.append(f"StoreQueue SAT complete-output success marker: {label}")
        if not any(receipt.get(key) is True for key in (
                "unconstrained", "unconstrained_marker", "free_input_marker_in_full_output")):
            failures.append(f"StoreQueue SAT no-assumption marker: {label}")
    if expected_miter_sha256 is not None:
        if receipt.get("miter_sha256") != expected_miter_sha256:
            failures.append(f"StoreQueue formal miter binding: {label}")


def verify_storequeue_composition(
    payload: dict[str, Any],
    verified_sources: dict[str, Any],
    reference_lock: dict[str, Any],
    validator_dependencies: dict[str, Any],
    rendered_artifacts: dict[str, str] | None,
    failures: list[str],
) -> bool:
    """Fail-closed audit for StoreQueue's leaf-theorem plus parent-glue proof."""

    if payload.get("build_id") != STOREQUEUE_BUILD_ID:
        failures.append("StoreQueue composition Build identity")
    if nested(payload, "audit_policy", "proof_decomposition") != STOREQUEUE_PROFILE:
        failures.append("StoreQueue composition profile")
    if payload.get("validator") != STOREQUEUE_VALIDATOR_PATH:
        failures.append("StoreQueue composition validator identity")
    if nested(payload, "audit_policy", "require_negative_control") is not True \
            or nested(payload, "audit_policy", "require_two_sided_negative_control") is not True:
        failures.append("StoreQueue profile must require both negative controls")

    source_bindings = nested(payload, "checks", "parent_composition", "bindings")
    if not isinstance(source_bindings, dict):
        failures.append("StoreQueue source bindings missing")
        source_bindings = {}
    _check_source_binding(
        source_bindings.get("python_build"), verified_sources.get("python_build"),
        "python_build", failures, STOREQUEUE_BUILD_PATH)
    _check_source_binding(
        source_bindings.get("validator"), verified_sources.get("validator"),
        "validator", failures, STOREQUEUE_VALIDATOR_PATH)
    _check_source_binding(
        source_bindings.get("locked_parent"), reference_lock.get("SQDataModule"),
        "SQDataModule", failures, "validation/reference-sv/SQDataModule.sv")
    _check_source_binding(
        source_bindings.get("locked_child"), reference_lock.get("SQData8Module"),
        "SQData8Module", failures, "validation/reference-sv/SQData8Module.sv")

    sources = payload.get("sources", {})
    dependency_records = sources.get("validator_dependencies", {}) if isinstance(sources, dict) else {}
    if isinstance(dependency_records, dict):
        for name, record in dependency_records.items():
            relative = str(record.get("path", "")).replace("\\", "/") \
                if isinstance(record, dict) else ""
            if ".work/" in relative or relative.startswith("validation/.work"):
                failures.append(f"StoreQueue counted dependency is transient: {name}")
    for dependency_name, dependency_path in (
            ("composition_validator", STOREQUEUE_COMPOSITION_VALIDATOR_PATH),
            ("strict_family_rail", STOREQUEUE_RAIL_PATH)):
        dependency = validator_dependencies.get(dependency_name)
        if not isinstance(dependency, dict) or dependency.get("status") != "PASS":
            failures.append(f"StoreQueue validator dependency missing: {dependency_name}")
        elif dependency.get("path") != dependency_path:
            failures.append(f"StoreQueue validator dependency identity: {dependency_name}")

    scope = payload.get("scope", {})
    if not isinstance(scope, dict):
        scope = {}
    public = scope.get("public_variants")
    variants = scope.get("variants")
    if public != list(STOREQUEUE_MEMBERS):
        failures.append("StoreQueue member list must match all four Build variants")
    if scope.get("variant_count") != len(STOREQUEUE_MEMBERS):
        failures.append("StoreQueue variant_count")
    if not isinstance(variants, dict) or set(variants) != set(STOREQUEUE_MEMBERS):
        failures.append("StoreQueue variant records must cover exactly four members")
        variants = variants if isinstance(variants, dict) else {}
    build_sha256 = verified_sources.get("python_build", {}).get("observed_sha256") \
        if isinstance(verified_sources.get("python_build"), dict) else None
    for member in STOREQUEUE_MEMBERS:
        raw = variants.get(member)
        if not isinstance(raw, dict):
            failures.append(f"StoreQueue variant record missing: {member}")
            continue
        if raw.get("source_build_sha256") != build_sha256 or not valid_sha256(build_sha256):
            failures.append(f"StoreQueue variant is not bound to current Build: {member}")
        locked = reference_lock.get(member)
        if not isinstance(locked, dict) or locked.get("status") != "PASS":
            failures.append(f"StoreQueue locked reference is not current: {member}")
        else:
            expected_ref = f"validation/reference-sv/{member}.sv"
            if raw.get("locked_reference") != expected_ref:
                failures.append(f"StoreQueue variant reference path: {member}")
            if raw.get("locked_sha256") != locked.get("observed_sha256"):
                failures.append(f"StoreQueue variant reference digest: {member}")
        expected_method = (STOREQUEUE_COMPOSED_METHOD if member == "SQDataModule"
                           else "sequential_equivalence")
        if raw.get("method") != expected_method or raw.get("sequential") is not True:
            failures.append(f"StoreQueue variant proof method: {member}")

    parent = variants.get("SQDataModule") if isinstance(variants, dict) else None
    if isinstance(parent, dict):
        if not isinstance(parent.get("sat"), dict):
            failures.append("StoreQueue parent member lacks its glue SAT receipt")
        if parent.get("verdict") != "PASS" or parent.get("success_marker") is not True:
            failures.append("StoreQueue parent member verdict")

    receipt = nested(payload, "checks", "parent_composition")
    if not isinstance(receipt, dict):
        failures.append("StoreQueue parent composition receipt missing")
        receipt = {}
    if receipt.get("status") != "PASS":
        failures.append("StoreQueue parent composition status")
    if receipt.get("method") != STOREQUEUE_GLUE_METHOD:
        failures.append("StoreQueue parent composition method")

    coverage = receipt.get("coverage")
    if not isinstance(coverage, dict):
        failures.append("StoreQueue composition coverage missing")
        coverage = {}
    lane_list = list(STOREQUEUE_LANES)
    ports_per_lane = [32] * len(STOREQUEUE_LANES)
    coverage_equalities = {
        "required_lanes": len(STOREQUEUE_LANES),
        "dut_lanes": lane_list,
        "reference_lanes": lane_list,
        "inline_child_lanes": lane_list,
        "named_child_ports_per_lane": 32,
        "dut_child_ports_by_lane": ports_per_lane,
        "reference_child_ports_by_lane": ports_per_lane,
        "dut_child_ports_exact": True,
        "reference_child_ports_exact": True,
        "inline_children_match_standalone": True,
        "expected_parent_output_names": 100,
        "dut_parent_output_names_covered": 100,
        "reference_parent_output_names_covered": 100,
        "expected_dut_parent_output_bits": 720,
        "covered_dut_parent_output_bits": 720,
        "expected_reference_parent_output_bits": 720,
        "covered_reference_parent_output_bits": 720,
        "expected_shared_child_output_bits": 720,
        "covered_shared_child_output_bits": 720,
        "all_outputs_covered": True,
    }
    for field, expected in coverage_equalities.items():
        if coverage.get(field) != expected:
            failures.append(f"StoreQueue composition coverage: {field}")
    parent_outputs = parent.get("outputs_compared", {}) if isinstance(parent, dict) else {}
    output_widths_valid = isinstance(parent_outputs, dict) and all(
        isinstance(width, int) and not isinstance(width, bool) and width > 0
        for width in parent_outputs.values())
    if (not output_widths_valid or len(parent_outputs) != 100
            or sum(parent_outputs.values()) != 720):
        failures.append("StoreQueue parent scope must compare all 100 outputs / 720 bits")

    artifacts = source_bindings.get("artifacts")
    if not isinstance(artifacts, dict):
        failures.append("StoreQueue generated artifact bindings missing")
        artifacts = {}
    if rendered_artifacts is None:
        failures.append("StoreQueue deterministic miter regeneration failed")
    else:
        for name in STOREQUEUE_ARTIFACTS:
            record = artifacts.get(name)
            rendered = rendered_artifacts.get(name)
            if not isinstance(record, dict) or not isinstance(rendered, str):
                failures.append(f"StoreQueue generated artifact receipt missing: {name}")
                continue
            expected_sha256 = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
            expected_bytes = len(rendered.encode("utf-8"))
            if record.get("sha256") != expected_sha256:
                failures.append(f"StoreQueue regenerated artifact digest: {name}")
            if record.get("bytes") != expected_bytes:
                failures.append(f"StoreQueue regenerated artifact byte count: {name}")
            if not isinstance(record.get("path"), str) or not record.get("path"):
                failures.append(f"StoreQueue generated artifact provenance path: {name}")

    formal = receipt.get("formal")
    if not isinstance(formal, dict):
        failures.append("StoreQueue parent composition formal receipts missing")
        formal = {}
    base_sat = formal.get("base_sat")
    base_miter_sha = artifacts.get("base_glue_miter", {}).get("sha256") \
        if isinstance(artifacts.get("base_glue_miter"), dict) else None
    _check_storequeue_formal_receipt(base_sat, "base parent glue", failures,
                                     sat=True, expected_miter_sha256=base_miter_sha)
    raw_sat = parent.get("sat") if isinstance(parent, dict) else None
    if isinstance(base_sat, dict) and isinstance(raw_sat, dict):
        for field in ("status", "returncode", "command", "formal_success_marker",
                      "sat_success_marker", "unconstrained", "output_sha256", "miter_sha256"):
            if raw_sat.get(field) != base_sat.get(field):
                failures.append(f"StoreQueue parent SAT receipt mismatch: {field}")
    top_sat = nested(payload, "checks", "formal", "yosys_formal_miter")
    if not isinstance(top_sat, dict):
        failures.append("StoreQueue top-level glue SAT receipt missing")
    else:
        if top_sat.get("mitered_variants") != 1:
            failures.append("StoreQueue glue SAT must cover exactly one parent member")
        if isinstance(base_sat, dict):
            for field in ("status", "returncode", "command", "formal_success_marker",
                          "sat_success_marker", "unconstrained", "output_sha256"):
                if top_sat.get(field) != base_sat.get(field):
                    failures.append(f"StoreQueue top-level SAT receipt mismatch: {field}")

    if rendered_artifacts is not None:
        for name, expected in STOREQUEUE_NEGATIVE_CONTROLS.items():
            control = formal.get(name)
            if not isinstance(control, dict):
                failures.append(f"StoreQueue negative-control receipt missing: {name}")
                continue
            if control.get("status") != "PASS":
                failures.append(f"StoreQueue negative-control status: {name}")
            if control.get("mutation_applied") is not True:
                failures.append(f"StoreQueue negative-control mutation not applied: {name}")
            if control.get("mutation") != {key: expected[key]
                                             for key in ("side", "lane", "port", "expression")}:
                failures.append(f"StoreQueue negative-control mutation identity: {name}")
            if not any(control.get(marker) is True
                       for marker in ("model_found", "model_found_marker")):
                failures.append(f"StoreQueue negative-control lacks explicit model: {name}")
            if control.get("success_marker_still_present") is not False \
                    and control.get("clean_proof_marker_disappeared") is not True:
                failures.append(f"StoreQueue negative-control retained clean proof: {name}")
            returncode = control.get("returncode")
            if not isinstance(returncode, int) or isinstance(returncode, bool):
                failures.append(f"StoreQueue negative-control returncode: {name}")
            if control.get("timed_out") is not False:
                failures.append(f"StoreQueue negative-control timeout: {name}")
            command = control.get("command", [])
            command_text = " ".join(str(item) for item in command) \
                if isinstance(command, list) else str(command)
            if "yosys" not in command_text or "sat -prove mismatch 0" not in command_text:
                failures.append(f"StoreQueue negative-control command: {name}")
            if not valid_sha256(control.get("output_sha256")):
                failures.append(f"StoreQueue negative-control full-output digest: {name}")
            if not isinstance(control.get("output_tail"), str) or not control.get("output_tail"):
                failures.append(f"StoreQueue negative-control output tail: {name}")
            miter_name = expected["miter"]
            expected_miter = artifacts.get(miter_name, {}).get("sha256") \
                if isinstance(artifacts.get(miter_name), dict) else None
            if control.get("miter_sha256") != expected_miter:
                failures.append(f"StoreQueue negative-control miter binding: {name}")

    detailed = nested(payload, "checks", "variants")
    if not isinstance(detailed, list) or len(detailed) != len(STOREQUEUE_MEMBERS):
        failures.append("StoreQueue detailed proof receipts must cover all four members")
    else:
        for member, detail in zip(STOREQUEUE_MEMBERS, detailed, strict=True):
            if member not in STOREQUEUE_LEAF_MEMBERS:
                continue
            proof = detail.get("yosys_equiv") if isinstance(detail, dict) else None
            if not isinstance(proof, dict):
                failures.append(f"StoreQueue leaf proof receipt missing: {member}")
                continue
            if proof.get("status") != "PASS" or proof.get("returncode") != 0 \
                    or proof.get("timed_out") is not False:
                failures.append(f"StoreQueue leaf proof did not complete: {member}")
            if proof.get("formal_success_marker") is not True:
                failures.append(f"StoreQueue leaf formal marker: {member}")
            markers = proof.get("markers_present")
            if not isinstance(markers, dict) or not all(
                    markers.get(marker) is True for marker in EQUIV_SUCCESS_MARKERS):
                failures.append(f"StoreQueue leaf full-output markers: {member}")
            total = proof.get("equiv_cells")
            proven = proof.get("proven_cells")
            unproven = proof.get("unproven_cells")
            if (not isinstance(total, int) or isinstance(total, bool) or total <= 0
                    or proven != total or unproven != 0):
                failures.append(f"StoreQueue leaf cells are not fully proven: {member}")
            if not valid_sha256(proof.get("output_sha256")):
                failures.append(f"StoreQueue leaf full-output digest: {member}")
            if not isinstance(proof.get("output_tail"), str) or not proof.get("output_tail"):
                failures.append(f"StoreQueue leaf output tail: {member}")
            command = proof.get("command", [])
            command_text = " ".join(str(item) for item in command) \
                if isinstance(command, list) else str(command)
            if "yosys" not in command_text or "equiv_induct" not in command_text \
                    or "equiv_status -assert" not in command_text:
                failures.append(f"StoreQueue leaf proof command: {member}")
            raw = variants.get(member, {})
            if isinstance(raw, dict):
                raw_cells = raw.get("unconstrained_or_cells", raw.get("unconstrained_or_equiv_cells"))
                if raw_cells != total or raw.get("proven_cells") != proven \
                        or raw.get("unproven_cells") != unproven:
                    failures.append(f"StoreQueue leaf scope/detail proof mismatch: {member}")
                if raw.get("markers_present") != markers:
                    failures.append(f"StoreQueue leaf scope/detail marker mismatch: {member}")

    return not failures


def current_flow_receipt(payload: dict[str, Any]) -> bool:
    """Recognize a new flow execution by its current producer and direct gates."""

    if payload.get("proof_execution_profile") != "RECOVERABLE_STRICT_FAMILY_V2":
        return False
    checks = payload.get("checks", {})
    stages = checks.get("stages") if isinstance(checks, dict) else None
    if not isinstance(stages, dict) or not isinstance(stages.get("tool_versions"), dict):
        return False
    direct = checks.get("direct_test", {})
    if (not isinstance(direct, dict) or direct.get("status") != "PASS"
            or type(direct.get("returncode")) is not int or direct["returncode"] != 0):
        return False
    sources = payload.get("sources", {})
    if not isinstance(sources, dict):
        return False
    dependencies = sources.get("validator_dependencies", {})
    if not isinstance(dependencies, dict):
        return False
    records = [sources.get("python_build"), sources.get("validator"),
               dependencies.get("strict_family_rail"), dependencies.get("direct_test")]
    for record in records:
        if not isinstance(record, dict) or record.get("producer_snapshot") is not None:
            return False
        path = (ROOT / str(record.get("path", ""))).resolve()
        try:
            path.relative_to(ROOT.resolve())
        except ValueError:
            return False
        if not path.is_file() or sha256(path) != record.get("sha256"):
            return False
    return True


def verify_proof_origin(payload: dict[str, Any], evidence_path: Path,
                        failures: list[str]) -> bool:
    """Check a relocation against its exact Git receipt, preserving proof data."""

    origin = payload.get("proof_origin")
    if origin is None:
        naming = json.loads((ROOT / "UHSC-Naming-Manifest.json").read_text(encoding="utf-8"))
        historical_paths = {item["new_path"] for item in
                            naming["path_rename_transaction"]["evidence_rebindings"]}
        if (evidence_path.relative_to(ROOT).as_posix() in historical_paths
                and not current_flow_receipt(payload)):
            failures.append("historical receipt is missing its pinned proof origin")
        return False
    if not isinstance(origin, dict):
        failures.append("invalid proof origin")
        return False
    revision = str(origin.get("revision", ""))
    original_path = str(origin.get("path", ""))
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None \
            or not original_path.startswith("validation/") \
            or ".." in Path(original_path).parts:
        failures.append("unsafe proof origin")
        return False
    try:
        naming = json.loads((ROOT / "UHSC-Naming-Manifest.json").read_text(encoding="utf-8"))
        transaction = naming["path_rename_transaction"]
        mapping = {item["old_path"]: item["new_path"] for item in transaction["renames"]}
        if revision != RELOCATION_BASELINE or transaction.get("baseline_revision") != revision:
            raise ValueError("proof origin differs from the relocation baseline")
        result = subprocess.run(["git", "show", f"{revision}:{original_path}"],
                                cwd=ROOT, capture_output=True, check=True)
        raw = result.stdout
        if hashlib.sha256(raw).hexdigest() != origin.get("sha256"):
            raise ValueError("original proof receipt digest")
        if evidence_path.relative_to(ROOT).as_posix() != mapping.get(original_path, original_path):
            raise ValueError("original proof receipt path")
        expected = json.loads(raw)
        relocation_records = [item for item in transaction["evidence_rebindings"]
                              if item["old_path"] == original_path]
        if (len(relocation_records) != 1
                or relocation_records[0].get("origin_sha256") != origin.get("sha256")
                or relocation_records[0].get("status") != expected.get("status")
                or relocation_records[0].get("new_path") != evidence_path.relative_to(ROOT).as_posix()):
            raise ValueError("proof origin differs from its relocation receipt")
        expected["proof_origin"] = origin
        expected["validator"] = mapping.get(expected["validator"], expected["validator"])
        sources = expected.get("sources", {})
        records = [(name, record) for name, record in sources.items()
                   if name in {"python_build", "validator", "scala", "reference_sv"}
                   and isinstance(record, dict)]
        dependencies = sources.get("validator_dependencies", {})
        if isinstance(dependencies, dict):
            records.extend(("validator_dependency." + name, record)
                           for name, record in dependencies.items() if isinstance(record, dict))
        for label, record in records:
            old_path = str(record.get("path", ""))
            record["path"] = mapping.get(old_path, old_path)
            actual = (payload.get("sources", {}).get(label)
                      if not label.startswith("validator_dependency.") else
                      payload.get("sources", {}).get("validator_dependencies", {}).get(
                          label.removeprefix("validator_dependency.")))
            snapshot = actual.get("producer_snapshot") if isinstance(actual, dict) else None
            representation = actual.get("representation_rebinding") if isinstance(actual, dict) else None
            if representation is not None:
                if label != "python_build" or not isinstance(representation, dict):
                    raise ValueError("representation rebinding is only valid for DUT sources")
                original_source = subprocess.run(
                    ["git", "show", f"{revision}:{old_path}"], cwd=ROOT,
                    capture_output=True, check=True).stdout
                current_source = (ROOT / record["path"]).read_bytes()
                if hashlib.sha256(original_source).hexdigest() != record.get("sha256"):
                    raise ValueError("DUT source was already stale at relocation baseline")
                original_ast = ast.dump(ast.parse(original_source), include_attributes=False)
                current_ast = ast.dump(ast.parse(current_source), include_attributes=False)
                if original_ast != current_ast:
                    raise ValueError("DUT representation rebinding changed its executable AST")
                ast_hash = hashlib.sha256(current_ast.encode("utf-8")).hexdigest()
                expected_representation = {
                    "method": "EXECUTABLE_AST_IDENTICAL",
                    "before_sha256": record["sha256"],
                    "after_sha256": hashlib.sha256(current_source).hexdigest(),
                    "executable_ast_sha256": ast_hash,
                }
                if representation != expected_representation:
                    raise ValueError("DUT representation rebinding receipt")
                record["sha256"] = expected_representation["after_sha256"]
                record["bytes"] = len(current_source)
                record["representation_rebinding"] = expected_representation
            if snapshot is not None:
                if label != "validator" and not label.startswith("validator_dependency."):
                    raise ValueError("producer archive cannot replace DUT or locked sources")
                producer = subprocess.run(["git", "show", f"{revision}:{old_path}"],
                                          cwd=ROOT, capture_output=True, check=True).stdout
                if hashlib.sha256(producer).hexdigest() != record.get("sha256"):
                    raise ValueError("producer was stale before the relocation")
                digest = record["sha256"]
                archive_path = ("validation/validation-Proof.Producer/"
                                f"validation-Proof.Producer-{digest}.txt")
                expected_snapshot = {"path": archive_path, "revision": revision,
                                     "origin_path": old_path, "sha256": digest}
                if snapshot != expected_snapshot:
                    raise ValueError("producer archive origin or digest")
                record["producer_snapshot"] = expected_snapshot
        bindings = expected.get("checks", {}).get("parent_composition", {}).get("bindings", {})
        for record in bindings.values():
            if isinstance(record, dict) and isinstance(record.get("path"), str):
                record["path"] = mapping.get(record["path"], record["path"])
        if payload != expected:
            raise ValueError("relocation changed proof conclusions, commands, logs or coverage")
    except (OSError, KeyError, ValueError, TypeError, subprocess.CalledProcessError) as error:
        failures.append(f"proof origin: {error}")
        return False
    return True


def verify_source(record: Any, label: str, failures: list[str], *,
                  proof_origin_verified: bool = False) -> dict[str, Any]:
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
    producer = record.get("producer_snapshot")
    if producer is not None:
        if (not proof_origin_verified or not isinstance(producer, dict)
                or (label != "validator" and not label.startswith("validator_dependency."))):
            failures.append(f"unauthorized producer snapshot: {label}")
        else:
            snapshot_path = (ROOT / str(producer.get("path", ""))).resolve()
            try:
                snapshot_path.relative_to((ROOT / "validation/validation-Proof.Producer").resolve())
                path = snapshot_path
            except ValueError:
                failures.append(f"producer snapshot outside archive: {label}")
                inside_root = False
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
        "producer_snapshot": producer,
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


def verify_record_map(records: Any, label: str, failures: list[str], *,
                      proof_origin_verified: bool = False) -> dict[str, Any]:
    """Verify every path/digest entry in a named evidence mapping."""

    if not isinstance(records, dict):
        return {}
    return {str(name): verify_source(record, f"{label}.{name}", failures,
                                    proof_origin_verified=proof_origin_verified)
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


def verify_variant_scope(payload: dict[str, Any], failures: list[str], counted: bool,
                         storequeue_composition: bool = False) -> dict[str, Any]:
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
        if raw.get("method") == STOREQUEUE_COMPOSED_METHOD:
            if (not storequeue_composition or str(name) != "SQDataModule"
                    or raw.get("sequential") is not True):
                member_failures.append("invalid StoreQueue compositional member proof")
        elif storequeue_composition and str(name) == "SQDataModule":
            member_failures.append("StoreQueue parent must use compositional member proof")
        sat = raw.get("sat")
        if isinstance(sat, dict):
            if type(sat.get("returncode")) is not int or sat.get("returncode") != 0 \
                    or sat.get("status") != "PASS":
                member_failures.append("SAT status")
            if sat.get("formal_success_marker") is not True or sat.get("unconstrained") is not True:
                member_failures.append("SAT completeness")
        elif "method" in raw:
            if raw.get("verdict") != "PASS" or raw.get("success_marker") is not True:
                member_failures.append("formal verdict")
            if raw.get("sequential"):
                if raw.get("method") == STOREQUEUE_COMPOSED_METHOD and isinstance(sat, dict):
                    # The specialized receipt is checked against the exact generated
                    # glue miter below; do not mislabel its SAT result as an inductive
                    # cell proof for the physically sequential parent.
                    pass
                else:
                    cells = raw.get("unconstrained_or_cells", raw.get("unconstrained_or_equiv_cells"))
                    if not isinstance(cells, int) or isinstance(cells, bool) or cells <= 0:
                        member_failures.append("zero/missing equivalence cells")
                    proven = raw.get("proven_cells")
                    if not isinstance(proven, int) or isinstance(proven, bool) or proven != cells:
                        member_failures.append("incomplete proven equivalence cells")
                    if type(raw.get("unproven_cells")) is not int or raw.get("unproven_cells") != 0:
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
        if (counted and payload.get("proof_execution_profile") == "RECOVERABLE_STRICT_FAMILY_V2"
                and raw.get("method") != STOREQUEUE_COMPOSED_METHOD):
            detail = detailed_by_name.get(str(name), {})
            member_proof = (detail.get("yosys_equiv") if raw.get("sequential")
                            else detail.get("sat_miter")) if isinstance(detail, dict) else None
            if (not isinstance(member_proof, dict) or member_proof.get("status") != "PASS"
                    or type(member_proof.get("returncode")) is not int
                    or member_proof.get("returncode") != 0
                    or member_proof.get("timed_out") is True
                    or member_proof.get("formal_success_marker") is not True
                    or not valid_sha256(member_proof.get("output_sha256"))):
                member_failures.append("current member proof receipt is incomplete")
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
    proof_origin_verified = verify_proof_origin(payload, path, failures)
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
        name: verify_source(record, name, failures,
                            proof_origin_verified=proof_origin_verified)
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
    validator_dependencies = verify_record_map(
        sources.get("validator_dependencies", {}) if isinstance(sources, dict) else {},
        "validator_dependency", failures, proof_origin_verified=proof_origin_verified)
    reference_lock = verify_reference_lock(payload, failures)
    declared_scala = verify_declared_scala(payload, failures, counted=not non_counting)
    scope_variants = nested(payload, "scope", "variants")
    has_composed_member = isinstance(scope_variants, dict) and any(
        isinstance(record, dict)
        and record.get("method") == STOREQUEUE_COMPOSED_METHOD
        for record in scope_variants.values())
    declared_storequeue_profile = nested(
        payload, "audit_policy", "proof_decomposition") == STOREQUEUE_PROFILE
    storequeue_composition = (
        build_id == STOREQUEUE_BUILD_ID and declared_storequeue_profile)
    if not non_counting and (declared_storequeue_profile or has_composed_member) \
            and not storequeue_composition:
        failures.append("StoreQueue composition profile is not bound to its exact Build")
    variant_checks = verify_variant_scope(
        payload, failures, counted=not non_counting,
        storequeue_composition=storequeue_composition)
    if not non_counting and storequeue_composition:
        rendered_artifacts: dict[str, str] | None = None
        if (validator_path == STOREQUEUE_VALIDATOR_PATH
                and verified_sources.get("validator", {}).get("status") == "PASS"
                and verified_sources.get("python_build", {}).get("status") == "PASS"):
            try:
                rendered_artifacts = render_storequeue_composition_artifacts(
                    ROOT / STOREQUEUE_BUILD_PATH)
            except Exception as error:  # A failed re-render must make the record non-counting.
                failures.append(
                    "StoreQueue proof-input regeneration failed: "
                    f"{type(error).__name__}: {error}")
        else:
            failures.append("StoreQueue proof-input sources are not current")
        verify_storequeue_composition(
            payload, verified_sources, reference_lock, validator_dependencies,
            rendered_artifacts, failures)
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
    catalog_scope = (
        isinstance(public_for_gates, list)
        and len(public_for_gates) >= 1
        and isinstance(variants_for_gates, dict)
        and set(str(item) for item in public_for_gates) == set(variants_for_gates)
    )
    catalog_variant_set = (
        catalog_scope
        and all(isinstance(record, dict) and "method" in record
                for record in variants_for_gates.values())
    )
    all_sequential_variants = (
        catalog_variant_set
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
        if not catalog_scope:
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
        build_name = Path(claimed_build).name
        for prefix in ("Cpu-Core-", "Cpu-Memory-"):
            if build_name.startswith(prefix):
                build_name = "Build-Cpu." + build_name.removeprefix(prefix)
                break
        expected_build_id = re.sub(r"-Hardware\.py$", "", build_name)
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
        if type(formal.get("returncode")) is not int or formal.get("returncode") != 0 \
                or formal.get("status") != "PASS":
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
            expected_mitered = (1 if storequeue_composition
                                else combinational if combinational else len(public))
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
        "proof_origin_verified": proof_origin_verified,
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
        "validator_dependencies": validator_dependencies,
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
