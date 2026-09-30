"""Unit checks for the shared strict-family section-5C reference view."""

from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_strict_family_rail as rail  # noqa: E402
from v2_strict_family_rail import synthesizable_view  # noqa: E402


class StrictFamilyReferenceViewTest(unittest.TestCase):
    """Keep automatic-declaration rewriting lossless and source-counted."""

    def test_locked_pmp_checker_multiline_initializers(self) -> None:
        reference = Path(__file__).resolve().parent / "reference-sv/PMPChecker_2.sv"
        view, audit = synthesizable_view(
            reference.read_text(encoding="utf-8"), "PMPChecker_2", True
        )
        self.assertTrue(audit["line_conservation_ok"])
        self.assertTrue(audit["register_update_equations_preserved"])
        self.assertTrue(audit["view_trusted"])
        self.assertNotIn("automatic logic", view)
        self.assertIn("reg res_pmp_is_match;", view)
        self.assertIn("res_pmp_is_match = \n(io_check_env_pmp_0_cfg_a[1]", view)

    def test_multiline_expression_lines_are_preserved(self) -> None:
        source = """module Demo(
  input clock,
  input [3:0] data,
  output out
);
  reg q;
  always @(posedge clock) begin
    automatic logic [1:0][3:0] lanes;
    automatic logic [3:0] temporary =
      data + 4'h1;
    lanes = {2{data}};
    q <= temporary[0];
  end
  assign out = q;
endmodule
"""
        view, audit = synthesizable_view(source, "Demo", False)
        self.assertTrue(audit["view_trusted"])
        self.assertIn("reg [1:0][3:0]  lanes;", view)
        self.assertIn("reg [3:0]  temporary;", view)
        self.assertIn("temporary = \ndata + 4'h1;", view)
        self.assertEqual(audit["code_lines_view"], audit["code_lines_locked"] + 1)

    def test_multiline_plain_declaration_catalogs_are_trusted(self) -> None:
        for name in ("CtrlBlock", "LoadQueueRAW"):
            reference = Path(__file__).resolve().parent / f"reference-sv/{name}.sv"
            view, audit = synthesizable_view(
                reference.read_text(encoding="utf-8"), name, False
            )
            self.assertTrue(audit["line_conservation_ok"], name)
            self.assertTrue(audit["register_update_equations_preserved"], name)
            self.assertTrue(audit["view_trusted"], name)
            self.assertNotIn("automatic logic", view)


class StrictFamilyRailCheckpointTest(unittest.TestCase):
    """Checkpoint reuse must be source-checked and strict-pass-only."""

    def test_hierarchy_outputs_receive_two_sided_negative_controls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = rail.FamilyRail(root / "unused.py", "Build.Test", root / "out.json",
                                     root / "unused.scala")
            runner.work = root
            paths = {side: root / f"{side}.sv" for side in ("target", "reference")}
            for side, prefix in (("target", "DUT"), ("reference", "REF")):
                paths[side].write_text(
                    f"module {prefix}_Demo(input clock, output [3:0] out);\n"
                    "Child child(.out(out));\nendmodule\n", encoding="utf-8")
            item = {"name": "Demo", "outputs": {"out": 4}, "sequential": True, **paths}

            def reject_mutant(command: list[str]) -> dict[str, object]:
                mutant = next(root.glob("MUTANT_sequential_*.sv"))
                # Both generated files are checked after the control below.
                self.assertIn("assign out = ~negative_control_out;", mutant.read_text())
                return {"status": "FAIL", "returncode": 1,
                        "equiv_failure_marker": True,
                        "equiv_success_markers": {marker: False for marker in rail.EQUIV_MARKERS}}

            with patch.object(rail, "wsl_path", side_effect=lambda path: path.as_posix()), \
                    patch.object(rail, "run_wsl", side_effect=reject_mutant):
                result = runner.negative_control([item])
            self.assertTrue(runner.controls_result_pass(result, [item]))
            for side in ("target", "reference"):
                mutant = (root / f"MUTANT_sequential_{side}.sv").read_text()
                self.assertIn(".out(negative_control_out)", mutant)
                self.assertIn("wire [3:0] negative_control_out;", mutant)

    def test_aggregate_cache_rechecks_proof_and_member_coverage(self) -> None:
        items = [{"sequential": False}]
        receipt = {"status": "PASS", "returncode": 0,
                   "formal_success_marker": True, "sat_success_marker": True,
                   "unconstrained": True, "mitered_variants": 1,
                   "command": ["yosys", "-p", "sat -prove mismatch 0"]}
        self.assertTrue(rail.FamilyRail.aggregate_result_pass(receipt, items))
        for key, value in (("returncode", None), ("formal_success_marker", False),
                           ("unconstrained", False), ("mitered_variants", 0)):
            with self.subTest(field=key):
                self.assertFalse(rail.FamilyRail.aggregate_result_pass(
                    {**receipt, key: value}, items))

    def test_control_cache_rechecks_applied_two_sided_mutations(self) -> None:
        case = {"status": "PASS", "mutation_applied": True,
                "explicit_failure_marker": True,
                "success_marker_still_present": False, "returncode": 1}
        receipt = {"status": "PASS", "cases": {
            "sequential.target": dict(case), "sequential.reference": dict(case)}}
        items = [{"sequential": True}]
        self.assertTrue(rail.FamilyRail.controls_result_pass(receipt, items))
        receipt["cases"]["sequential.reference"]["mutation_applied"] = False
        self.assertFalse(rail.FamilyRail.controls_result_pass(receipt, items))
        receipt["cases"].pop("sequential.reference")
        self.assertFalse(rail.FamilyRail.controls_result_pass(receipt, items))

    def test_wsl_path_conversion_is_reused_in_process(self) -> None:
        rail.WSL_PATH_CACHE.clear()
        with patch.object(
            rail.subprocess,
            "run",
            return_value=SimpleNamespace(stdout=b"/mnt/c/work/member.sv\n"),
        ) as run:
            first = rail.wsl_path(Path("C:/work/member.sv"))
            second = rail.wsl_path(Path("C:/work/member.sv"))
        self.assertEqual(first, "/mnt/c/work/member.sv")
        self.assertEqual(second, first)
        run.assert_called_once()
        rail.WSL_PATH_CACHE.clear()

    def test_prepared_files_are_rehashed_before_checkpoint_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = root / "Build.py"
            build.write_text("# synthetic test build\n", encoding="utf-8")
            runner = rail.FamilyRail(build, "Build.Test", root / "evidence.json", root / "source.scala")
            runner.work = root / "work"
            runner.cache_path = runner.work / "rail-checkpoint.json"
            runner.work.mkdir()
            paths = {name: runner.work / f"{name}.sv" for name in ("target", "reference", "miter")}
            for name, path in paths.items():
                path.write_text(f"module {name}; endmodule\n", encoding="utf-8")
            item = {
                "name": "Demo",
                **paths,
                "prepared_hashes": {name: rail.sha256_file(path) for name, path in paths.items()},
            }
            runner.cache_path.write_text(json.dumps({
                "schema_version": rail.CACHE_SCHEMA,
                "members": {"member-key": {"item": runner.path_value(item)}},
            }), encoding="utf-8")
            restored = runner.cached_item("member-key")
            if restored is None:
                self.fail("expected the intact prepared files to restore")
            self.assertEqual(restored["target"], paths["target"])
            paths["target"].write_text("tampered\n", encoding="utf-8")
            self.assertIsNone(runner.cached_item("member-key"))

    def test_member_cache_key_survives_unrelated_build_source_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = root / "Build.py"
            build.write_text("member A and member B implementations\n", encoding="utf-8")
            with patch.object(rail, "validation_tool_versions", return_value={"yosys": "test"}):
                runner = rail.FamilyRail(build, "Build.Test", root / "evidence.json", root / "missing.scala")
                args = ("PMPChecker_2", [], "module DUT_PMPChecker_2; endmodule\n",
                        "module REF_PMPChecker_2; endmodule\n", "module M; endmodule\n")
                first_key = runner.member_cache_key(*args)
                build.write_text("member A unchanged; unrelated member B changed\n", encoding="utf-8")
                second_key = runner.member_cache_key(*args)
                changed_key = runner.member_cache_key(
                    args[0], args[1], "module DUT_PMPChecker_2; assign x = 1'b1; endmodule\n",
                    args[3], args[4],
                )
        self.assertEqual(first_key, second_key)
        self.assertNotEqual(second_key, changed_key)

    def test_tool_version_change_invalidates_member_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = root / "Build.py"
            build.write_text("build source\n", encoding="utf-8")
            runner = rail.FamilyRail(build, "Build.Test", root / "evidence.json", root / "missing.scala")
            versions = [
                {"python": "3.13", "amaranth": "0.5", "yosys": "0.40", "verilator": "5.0"},
                {"python": "3.13", "amaranth": "0.5", "yosys": "0.41", "verilator": "5.0"},
            ]
            args = ("PMPChecker_2", [], "module DUT_PMPChecker_2; endmodule\n",
                    "module REF_PMPChecker_2; endmodule\n", "module M; endmodule\n")
            with patch.object(rail, "validation_tool_versions", side_effect=versions):
                first = runner.member_cache_key(*args)
                second = runner.member_cache_key(*args)
        self.assertNotEqual(first, second)
        self.assertFalse(rail.tool_versions_complete({"python": "3.13", "amaranth": "unavailable",
                                                       "yosys": "0.41", "verilator": "5.0"}))

    def test_formal_cache_requires_full_strict_success(self) -> None:
        item = {"abi_exact": True, "deterministic": True, "view_trusted": True,
                "sequential": True,
                "tool_versions": {"python": "3.13", "amaranth": "0.5",
                                  "yosys": "0.40", "verilator": "5.0"}}
        result = {
            "method": "sequential_equivalence",
            "verilator": {"status": "PASS"},
            "locked_verilator": {"status": "PASS"},
            "yosys_equiv": {
                "status": "PASS", "returncode": 0, "formal_success_marker": True,
                "markers_present": {marker: True for marker in rail.EQUIV_MARKERS},
                "equiv_cells": 4, "proven_cells": 4, "unproven_cells": 0,
                "command": ["yosys", "-p", "equiv_induct -undef; equiv_status -assert"],
            },
        }
        self.assertTrue(rail.FamilyRail.formal_result_pass(result, item))
        result["yosys_equiv"]["command"] = ["yosys", "-p", "equiv_simple -seq 1"]
        self.assertFalse(rail.FamilyRail.formal_result_pass(result, item))
        result["yosys_equiv"]["command"] = ["yosys", "-p", "equiv_induct -undef; equiv_status -assert"]
        result["yosys_equiv"]["markers_present"] = {}
        self.assertFalse(rail.FamilyRail.formal_result_pass(result, item))
        result["yosys_equiv"]["markers_present"] = {marker: True for marker in rail.EQUIV_MARKERS}
        result["yosys_equiv"]["returncode"] = None
        self.assertFalse(rail.FamilyRail.formal_result_pass(result, item))
        result["yosys_equiv"]["returncode"] = 0
        item["tool_versions"]["amaranth"] = "unavailable"
        self.assertFalse(rail.FamilyRail.formal_result_pass(result, item))

    def test_static_failure_stops_before_tool_invocation(self) -> None:
        runner = rail.FamilyRail(Path("unused.py"), "Build.Test", Path("unused.json"),
                                 Path("unused.scala"))
        with patch.object(rail, "run_wsl") as run_wsl:
            result = runner.prove({"name": "Demo", "sequential": False, "static_blocked": True})
        self.assertEqual(result["sat_miter"]["status"], "NOT_RUN")
        self.assertEqual(result["reason"], "static gate failed")
        run_wsl.assert_not_called()

    def test_failed_member_baseline_skips_aggregate_and_negative_controls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_root = rail.ROOT / "python/Program-System/System-Build/Build-Cpu"
            build = next(build_root.rglob("*.py"))
            runner = rail.FamilyRail(build, "Build.Test", root / "evidence.json", root / "missing.scala")
            runner.work = root / "work"
            runner.cache_path = runner.work / "rail-checkpoint.json"
            paths = {name: root / f"{name}.sv" for name in ("target", "reference", "miter")}
            for path in paths.values():
                path.write_text("module test; endmodule\n", encoding="utf-8")
            reference = rail.REF_DIR / "PMPChecker_2.sv"
            item = {
                "name": "PMPChecker_2", "inputs": {"clock": 1}, "outputs": {"out": 1},
                "children": [], "sequential": False, "abi_exact": True,
                "deterministic": True, "output_less": False, "miter_selfcheck": True,
                "view_trusted": True, "view_audits": [],
                "locked_sha256": rail.sha256_file(reference), "locked_sources": [reference],
                "target": paths["target"], "reference": paths["reference"],
                "miter": paths["miter"], "cache_key": "member-key", "cache_hit": False,
            }
            passed = {"status": "PASS"}

            def lint_gate(entry: dict[str, object]) -> tuple[dict[str, str], dict[str, str]]:
                entry["verilator"] = dict(passed)
                entry["locked_verilator"] = dict(passed)
                return dict(passed), dict(passed)

            failed = {
                "method": "sat_miter", "verilator": passed, "locked_verilator": passed,
                "sat_miter": {"status": "FAIL", "returncode": 1,
                              "formal_success_marker": False},
            }
            with patch.object(rail, "load_module", return_value=object()), \
                    patch.object(rail, "enumerate_members", return_value=["PMPChecker_2"]), \
                    patch.object(rail.py_compile, "compile"), \
                    patch.object(rail, "pyright_check", return_value=passed), \
                    patch.object(runner, "prepare", return_value=item), \
                    patch.object(runner, "lint_gate", side_effect=lint_gate), \
                    patch.object(runner, "cached_formal", return_value=None), \
                    patch.object(runner, "prove", return_value=failed), \
                    patch.object(runner, "remember_formal"), \
                    patch.object(runner, "aggregate") as aggregate, \
                    patch.object(runner, "negative_control") as negative_control:
                payload = runner.run()
            self.assertEqual(payload["status"], "STRICT_PENDING")
            aggregate.assert_not_called()
            negative_control.assert_not_called()


if __name__ == "__main__":
    unittest.main()
