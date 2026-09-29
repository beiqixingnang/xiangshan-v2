"""Regression tests for the strict-equivalence progress audit."""

from __future__ import annotations

import unittest
import json
from pathlib import Path
import sys
import copy
import hashlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_strict_equivalence_progress as progress


class BuildCatalogEnumerationTests(unittest.TestCase):
    """Keep dynamic Build catalogs from being reduced to regex fragments."""

    def test_regfile_runtime_catalog_has_every_locked_member(self) -> None:
        # This catalog is computed from embedded JSON and cannot be resolved by AST literals alone.
        build = Path(
            "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
            "Build-Cpu.Backend.Regfile.Regfile-Hardware.py"
        )
        failures: list[str] = []

        members = progress.build_declared_members(build, failures)

        self.assertEqual([], failures)
        self.assertEqual(97, len(members))
        self.assertIn("BusyTable", members)
        self.assertIn("RenameTable", members)
        self.assertIn("WbFuBusyTable", members)

    def test_single_sequential_catalog_uses_member_proof(self) -> None:
        plan = json.loads(progress.PLAN.read_text(encoding="utf-8"))
        expected_commit = plan["scan_freeze"]["source_commit"]
        evidence = progress.ROOT / (
            "validation/v2-build-cpu-backend-datapath-newpipelineconnect-strict-evidence.json"
        )

        result = progress.verify_evidence(evidence, expected_commit)

        self.assertEqual("PASS", result["status"], result["failures"])

    def test_specialized_aggregate_schema_stays_countable(self) -> None:
        plan = json.loads(progress.PLAN.read_text(encoding="utf-8"))
        expected_commit = plan["scan_freeze"]["source_commit"]
        evidence = progress.ROOT / "validation/v2-csa-family-strict-evidence.json"

        result = progress.verify_evidence(evidence, expected_commit)

        self.assertEqual("PASS", result["status"], result["failures"])


class StoreQueueCompositionAuditTests(unittest.TestCase):
    """Keep the specialized sequential-parent proof decomposition fail-closed."""

    @staticmethod
    def source_record(relative: str) -> dict[str, object]:
        path = progress.ROOT / relative
        return {"path": relative, "status": "PASS",
                "observed_sha256": progress.sha256(path)}

    @classmethod
    def fixture(cls):
        build = cls.source_record(progress.STOREQUEUE_BUILD_PATH)
        validator = cls.source_record(progress.STOREQUEUE_VALIDATOR_PATH)
        lock = {
            member: cls.source_record(f"validation/reference-sv/{member}.sv")
            for member in progress.STOREQUEUE_MEMBERS
        }
        build_path = progress.ROOT / progress.STOREQUEUE_BUILD_PATH
        validator_path = progress.ROOT / progress.STOREQUEUE_VALIDATOR_PATH
        bindings = {
            "python_build": {"path": build["path"], "sha256": build["observed_sha256"],
                             "bytes": build_path.stat().st_size},
            "validator": {"path": validator["path"], "sha256": validator["observed_sha256"],
                          "bytes": validator_path.stat().st_size},
            "locked_parent": {"path": lock["SQDataModule"]["path"],
                              "sha256": lock["SQDataModule"]["observed_sha256"],
                              "bytes": (progress.ROOT / lock["SQDataModule"]["path"]).stat().st_size},
            "locked_child": {"path": lock["SQData8Module"]["path"],
                             "sha256": lock["SQData8Module"]["observed_sha256"],
                             "bytes": (progress.ROOT / lock["SQData8Module"]["path"]).stat().st_size},
        }
        rendered = {name: f"deterministic {name}\n" for name in progress.STOREQUEUE_ARTIFACTS}
        bindings["artifacts"] = {
            name: {"path": f"validation/.work/storequeue-profile/{name}.sv",
                   "bytes": len(text.encode("utf-8")),
                   "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
            for name, text in rendered.items()
        }
        base_sha = bindings["artifacts"]["base_glue_miter"]["sha256"]
        base_sat = {
            "status": "PASS", "returncode": 0, "timed_out": False,
            "command": ["yosys", "-Q", "-p", "prep -top SQDataModule_GLUE_MITER; opt; sat -prove mismatch 0"],
            "formal_success_marker": True, "sat_success_marker": True,
            "unconstrained": True, "output_sha256": "a" * 64,
            "output_tail": progress.SUCCESS_MARKER + "\nFinal constraint equation: { } = { }",
            "miter_sha256": base_sha,
        }
        parent_outputs = {
            "io_rdata_0_mask": 16, "io_rdata_0_data": 128,
            "io_rdata_1_mask": 16, "io_rdata_1_data": 128,
            **{f"io_forwardMask_{forward}_{lane}": 1
               for forward in range(3) for lane in range(16)},
            **{f"io_forwardData_{forward}_{lane}": 8
               for forward in range(3) for lane in range(16)},
        }
        proof_markers = {marker: True for marker in progress.EQUIV_SUCCESS_MARKERS}
        leaf_cells = {"SQAddrModule": 3930, "SQAddrModule_1": 4032,
                      "SQData8Module": 1161}
        variants: dict[str, dict[str, object]] = {}
        details: list[dict[str, object]] = []
        for index, member in enumerate(progress.STOREQUEUE_MEMBERS):
            variants[member] = {
                "method": (progress.STOREQUEUE_COMPOSED_METHOD if member == "SQDataModule"
                           else "sequential_equivalence"),
                "sequential": True,
                "source_build_sha256": build["observed_sha256"],
                "locked_reference": lock[member]["path"],
                "locked_sha256": lock[member]["observed_sha256"],
                "inputs": {"clock": 1},
                "outputs_compared": parent_outputs if member == "SQDataModule" else {"out": 1},
                "sat": copy.deepcopy(base_sat) if member == "SQDataModule" else None,
                "verdict": "PASS", "success_marker": True,
            }
            if member in leaf_cells:
                count = leaf_cells[member]
                output_sha = f"{index + 16:064x}"
                proof = {
                    "status": "PASS", "returncode": 0, "timed_out": False,
                    "formal_success_marker": True, "markers_present": proof_markers,
                    "equiv_cells": count, "proven_cells": count, "unproven_cells": 0,
                    "output_sha256": output_sha, "output_tail": "Equivalence successfully proven!",
                    "command": ["yosys", "equiv_induct -undef; equiv_status -assert"],
                }
                variants[member].update({
                    "unconstrained_or_cells": count,
                    "proven_cells": count,
                    "unproven_cells": 0,
                    "markers_present": proof_markers,
                })
                details.append({"yosys_equiv": proof})
            else:
                details.append({"status": "PASS"})

        controls = {}
        for name, expected in progress.STOREQUEUE_NEGATIVE_CONTROLS.items():
            controls[name] = {
                "status": "PASS", "mutation_applied": True,
                "mutation": {key: expected[key]
                             for key in ("side", "lane", "port", "expression")},
                "model_found": True, "success_marker_still_present": False,
                "returncode": 0, "timed_out": False,
                "command": ["yosys", "sat -prove mismatch 0"],
                "output_sha256": "b" * 64, "output_tail": "model found: FAIL!",
                "miter_sha256": bindings["artifacts"][expected["miter"]]["sha256"],
            }
        coverage = {
            "required_lanes": 16,
            "dut_lanes": list(range(16)), "reference_lanes": list(range(16)),
            "inline_child_lanes": list(range(16)),
            "named_child_ports_per_lane": 32,
            "dut_child_ports_by_lane": [32] * 16,
            "reference_child_ports_by_lane": [32] * 16,
            "dut_child_ports_exact": True, "reference_child_ports_exact": True,
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
        payload = {
            "build_id": progress.STOREQUEUE_BUILD_ID,
            "validator": progress.STOREQUEUE_VALIDATOR_PATH,
            "audit_policy": {"proof_decomposition": progress.STOREQUEUE_PROFILE,
                             "require_negative_control": True,
                             "require_two_sided_negative_control": True},
            "sources": {"validator_dependencies": {}},
            "scope": {"public_variants": list(progress.STOREQUEUE_MEMBERS),
                      "variant_count": 4, "variants": variants},
            "checks": {"variants": details,
                       "parent_composition": {
                           "status": "PASS", "method": progress.STOREQUEUE_GLUE_METHOD,
                           "coverage": coverage,
                           "bindings": bindings,
                           "formal": {"base_sat": base_sat, **controls},
                       },
                       "formal": {"yosys_formal_miter": {
                           **base_sat, "mitered_variants": 1,
                       }}},
        }
        dependencies = {
            "composition_validator": cls.source_record(
                progress.STOREQUEUE_COMPOSITION_VALIDATOR_PATH),
            "strict_family_rail": cls.source_record(progress.STOREQUEUE_RAIL_PATH),
        }
        verified_sources = {"python_build": build, "validator": validator}
        return payload, verified_sources, lock, dependencies, rendered

    def test_storequeue_composition_receipt_is_fail_closed(self) -> None:
        payload, sources, locks, dependencies, rendered = self.fixture()

        failures: list[str] = []
        self.assertTrue(progress.verify_storequeue_composition(
            payload, sources, locks, dependencies, rendered, failures), failures)

        mutations = (
            lambda record: record["checks"]["parent_composition"]["coverage"].__setitem__(
                "inline_children_match_standalone", False),
            lambda record: record["checks"]["parent_composition"]["bindings"]["locked_parent"].__setitem__(
                "sha256", "0" * 64),
            lambda record: record["checks"]["parent_composition"]["formal"][
                "target_input_slice_mutation"].__setitem__("model_found", False),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                corrupted = copy.deepcopy(payload)
                mutate(corrupted)
                failures = []
                self.assertFalse(progress.verify_storequeue_composition(
                    corrupted, sources, locks, dependencies, rendered, failures))
                self.assertTrue(failures)

if __name__ == "__main__":
    unittest.main()
