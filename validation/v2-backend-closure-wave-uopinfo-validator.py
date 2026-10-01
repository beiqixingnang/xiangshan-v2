"""Focused RTL/reference validator for the UopInfoGen Decode leaf."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import re
import shutil
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Backend.Decode.ControlFamily-Hardware.py"
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
REFERENCE = ROOT / "validation/reference-sv/UopInfoGen.sv"
REFERENCE_DEPENDENCIES = (
    ROOT / "validation/reference-sv/strdiedLSNumOfUopTable.sv",
    ROOT / "validation/reference-sv/indexedLSNumOfUopTable.sv",
)
WORK = ROOT / "validation/.work/v2-backend-closure-wave-uopinfo"
EVIDENCE = ROOT / "validation/v2-backend-closure-wave-uopinfo.json"
LOCKED_XSTOP = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
LOCKED_XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_SHA256 = "062e2e6c46e9cb960597ad65bb5f74e9564b11a38d609300afa9b474144d4c75"
REFERENCE_DEPENDENCY_SHA256 = {
    "strdiedLSNumOfUopTable.sv": "ca943e5018de4f49ecc2d3e021b686cd0c2feefc9872e69957b2e7d92b257ba9",
    "indexedLSNumOfUopTable.sv": "79de7e9bad88c911664172dfb9b58cb08cbd565e79f7aed06d5fc38967eecbf2",
}
COMBINATIONAL_CASES = 64 * 8 * 4 * 8 * 8 * 8 * 4
COMPLEX_CASES = 8


def load_target() -> Any:
    spec = importlib.util.spec_from_file_location("v2_uopinfo_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_wsl(command: list[str], require_yosys_top: str | None = None) -> dict[str, object]:
    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", rendered],
        capture_output=True,
        check=False,
    )
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    record: dict[str, object] = {
        "command": command,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "output_tail": output[-2000:],
        "output_sha256": digest(output.encode()),
    }
    if require_yosys_top is not None:
        top_match = re.search(rf"=== {re.escape(require_yosys_top)} ===(?P<stats>.*?)(?:End of script|$)", output, re.DOTALL)
        stats = top_match.group("stats") if top_match else ""
        port_match = re.search(r"Number of ports:\s*(\d+)", stats)
        cell_match = re.search(r"Number of cells:\s*(\d+)", stats)
        validation = {
            "frontend_completed": "Successfully finished Verilog frontend" in output,
            "top_module_present": top_match is not None,
            "port_count": int(port_match.group(1)) if port_match else None,
            "expected_port_count": 15,
            "positive_cell_count": int(cell_match.group(1)) if cell_match else None,
        }
        valid = (
            result.returncode == 0
            and validation["frontend_completed"]
            and validation["top_module_present"]
            and validation["port_count"] == validation["expected_port_count"]
            and isinstance(validation["positive_cell_count"], int)
            and validation["positive_cell_count"] > 0
        )
        record["yosys_design_check"] = validation
        record["status"] = "PASS" if valid else "FAIL"
    return record


def wsl_path(path: Path) -> str:
    result = subprocess.run(
        ["wsl.exe", "-e", "wslpath", "-a", str(path.resolve())],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace"))
    return result.stdout.decode("utf-8", "replace").strip()


def run_pyright_exact_copy(target: Path) -> dict[str, object]:
    """Type-check one byte-identical temporary copy of the owned Build file."""

    with tempfile.TemporaryDirectory(prefix="uhsc_uopinfo_pyright_") as temp_root:
        copied = Path(temp_root) / target.name
        shutil.copyfile(target, copied)
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "pyright", "--outputjson", str(copied)],
            capture_output=True,
            check=False,
        )
        stdout = result.stdout.decode("utf-8", "replace")
        stderr = result.stderr.decode("utf-8", "replace")
        try:
            report = json.loads(stdout)
        except json.JSONDecodeError:
            report = {}
        summary = report.get("summary", {}) if isinstance(report, dict) else {}
        diagnostics = report.get("generalDiagnostics", []) if isinstance(report, dict) else []
        errors = [
            {
                "rule": item.get("rule"),
                "message": item.get("message"),
                "range": item.get("range"),
            }
            for item in diagnostics
            if item.get("severity") == "error"
        ]
        copied_hash = digest(copied.read_bytes())
        expected_hash = digest(target.read_bytes())
        files_analyzed = summary.get("filesAnalyzed")
        error_count = summary.get("errorCount")
        valid = (
            result.returncode == 0
            and copied_hash == expected_hash
            and files_analyzed == 1
            and error_count == 0
        )
        return {
            "command": ["cmd.exe", "/d", "/c", "pyright --outputjson <byte-identical temporary copy>"],
            "status": "PASS" if valid else "FAIL",
            "returncode": result.returncode,
            "copied_file_sha256": copied_hash,
            "target_file_sha256": expected_hash,
            "files_analyzed": files_analyzed,
            "error_count": error_count,
            "warning_count": summary.get("warningCount"),
            "errors": errors,
            "stderr_tail": stderr[-1000:],
        }


def make_testbench(ports: list[tuple[str, str, int]]) -> str:
    inputs = [port for port in ports if port[1] == "input"]
    outputs = [port for port in ports if port[1] == "output"]
    declarations = []
    dut_connections = []
    ref_connections = []
    for name, direction, width in inputs:
        shape = f"[{width - 1}:0] " if width > 1 else ""
        declarations.append(f"  reg {shape}{name};")
        dut_connections.append(f".{name}({name})")
        ref_connections.append(f".{name}({name})")
    for name, _direction, width in outputs:
        shape = f"[{width - 1}:0] " if width > 1 else ""
        declarations.extend((f"  wire {shape}dut_{name};", f"  wire {shape}ref_{name};"))
        dut_connections.append(f".{name}(dut_{name})")
        ref_connections.append(f".{name}(ref_{name})")
    output_dut = "{" + ", ".join(f"dut_{name}" for name, _direction, _width in outputs) + "}"
    output_ref = "{" + ", ".join(f"ref_{name}" for name, _direction, _width in outputs) + "}"
    dimensions = """
    integer split_value, vlmul_value, vsew_value, width_value;
    integer nf_value, vmvn_value, mode_value;
    integer complex_value, checked;
"""
    control_sweep = """
    initial begin
      checked = 0;
      io_in_preInfo_isVecArith = 0;
      io_in_preInfo_isVecMem = 0;
      io_in_preInfo_isAmoCAS = 0;
      for (split_value = 0; split_value < 64; split_value = split_value + 1)
        for (vlmul_value = 0; vlmul_value < 8; vlmul_value = vlmul_value + 1)
          for (vsew_value = 0; vsew_value < 4; vsew_value = vsew_value + 1)
            for (width_value = 0; width_value < 8; width_value = width_value + 1)
              for (nf_value = 0; nf_value < 8; nf_value = nf_value + 1)
                for (vmvn_value = 0; vmvn_value < 8; vmvn_value = vmvn_value + 1)
                  for (mode_value = 0; mode_value < 4; mode_value = mode_value + 1) begin
                    io_in_preInfo_typeOfSplit = split_value;
                    io_in_preInfo_vlmul = vlmul_value;
                    io_in_preInfo_vsew = vsew_value;
                    io_in_preInfo_vwidth = width_value;
                    io_in_preInfo_nf = nf_value;
                    io_in_preInfo_vmvn = vmvn_value;
                    io_in_preInfo_isVlsr = mode_value[1];
                    io_in_preInfo_isVlsm = mode_value[0];
                    #1;
                    if ({DUT_OUTPUTS} !== {REF_OUTPUTS})
                      $fatal(1, "UopInfoGen mismatch split=%0d vlmul=%0d vsew=%0d width=%0d nf=%0d vmvn=%0d mode=%0d dut=%h ref=%h", split_value, vlmul_value, vsew_value, width_value, nf_value, vmvn_value, mode_value, {DUT_OUTPUTS}, {REF_OUTPUTS});
                    checked = checked + 1;
                  end
      io_in_preInfo_typeOfSplit = 0;
      io_in_preInfo_vlmul = 0;
      io_in_preInfo_vsew = 0;
      io_in_preInfo_vwidth = 0;
      io_in_preInfo_nf = 0;
      io_in_preInfo_vmvn = 0;
      io_in_preInfo_isVlsr = 0;
      io_in_preInfo_isVlsm = 0;
      for (complex_value = 0; complex_value < 8; complex_value = complex_value + 1) begin
        io_in_preInfo_isVecArith = complex_value[0];
        io_in_preInfo_isVecMem = complex_value[1];
        io_in_preInfo_isAmoCAS = complex_value[2];
        #1;
        if ({DUT_OUTPUTS} !== {REF_OUTPUTS})
          $fatal(1, "UopInfoGen complexity mismatch flags=%0d dut=%h ref=%h", complex_value, {DUT_OUTPUTS}, {REF_OUTPUTS});
        checked = checked + 1;
      end
      if (checked != EXPECTED_CASES)
        $fatal(1, "UopInfoGen case count mismatch checked=%0d expected=%0d", checked, EXPECTED_CASES);
      $display("UOPINFO_LOCKED_DIFF_PASS cases=%0d", checked);
      $finish;
    end
"""
    body = control_sweep.replace("{DUT_OUTPUTS}", output_dut)
    body = body.replace("{REF_OUTPUTS}", output_ref)
    body = body.replace("EXPECTED_CASES", str(COMBINATIONAL_CASES + COMPLEX_CASES))
    return "\n".join(
        [
            "module uopinfo_diff_tb;",
            *declarations,
            dimensions,
            f"  UopInfoGen dut({', '.join(dut_connections)});",
            f"  UopInfoGen_reference reference({', '.join(ref_connections)});",
            body,
            "endmodule",
            "",
        ]
    )


def run_amaranth_direct(module: Any) -> dict[str, object]:
    """Exercise real Amaranth outputs against fixed leaf vectors."""

    dut = module.DecodeControlFamily("UopInfoGen")
    vectors = (
        ((0b010010, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0), (2, 2, 2, 0)),
        ((0b101111, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0), (8, 8, 2, 0)),
        ((0b110011, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0), (3, 3, 2, 0)),
        ((0b110111, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0), (4, 2, 1, 0)),
        ((0b000100, 0, 0, 0, 0, 7, 0, 0, 0, 0, 0), (8, 8, 1, 0)),
        ((0b000000, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0), (1, 1, 1, 1)),
    )
    input_names = (
        "io_in_preInfo_typeOfSplit", "io_in_preInfo_vlmul",
        "io_in_preInfo_vsew", "io_in_preInfo_vwidth",
        "io_in_preInfo_nf", "io_in_preInfo_vmvn",
        "io_in_preInfo_isVecArith", "io_in_preInfo_isVecMem",
        "io_in_preInfo_isAmoCAS", "io_in_preInfo_isVlsr",
        "io_in_preInfo_isVlsm",
    )
    output_names = (
        "io_out_uopInfo_numOfUop", "io_out_uopInfo_numOfWB",
        "io_out_uopInfo_lmul", "io_out_isComplex",
    )
    mismatches: list[dict[str, object]] = []

    async def bench(ctx: Any) -> None:
        for values, expected in vectors:
            for name, value in zip(input_names, values):
                ctx.set(dut.ports[name], value)
            await ctx.delay(1e-9)
            actual = tuple(ctx.get(dut.ports[name]) for name in output_names)
            if actual != expected:
                mismatches.append({"inputs": values, "expected": expected, "actual": actual})

    simulator = Simulator(dut)
    simulator.add_testbench(bench)
    simulator.run()
    return {"status": "PASS" if not mismatches else "FAIL", "vectors": len(vectors), "mismatches": mismatches}


def main() -> int:
    failures: list[str] = []
    module = load_target()
    reuse_reference_diff = "--reuse-reference-differential" in sys.argv[1:]
    py_compile.compile(str(TARGET), doraise=True)
    if tuple(module.IMPLEMENTED_MEMBERS) != ("UopInfoGen",):
        failures.append("implemented-member declaration mismatch")
    if hasattr(module, "uop_info_reference") or "uop_info_reference" in module.__all__:
        failures.append("behavior helper leaked into the Build API")
    direct = run_amaranth_direct(module)
    if direct["status"] != "PASS":
        failures.append("Amaranth direct vectors failed")
    pyright = run_pyright_exact_copy(TARGET)
    if pyright["status"] != "PASS":
        failures.append("single-file Pyright check failed")

    locked_hash = run_wsl(["sha256sum", LOCKED_XSTOP])
    actual_xstop_hash = str(locked_hash["output_tail"]).split()[0] if locked_hash["status"] == "PASS" else None
    if actual_xstop_hash != LOCKED_XSTOP_SHA256:
        failures.append("locked XSTop digest mismatch or unavailable")

    reference_bytes = REFERENCE.read_bytes()
    reference_hash = digest(reference_bytes)
    if reference_hash != REFERENCE_SHA256:
        failures.append("locked UopInfoGen reference digest mismatch")
    dependency_records = []
    for dependency in REFERENCE_DEPENDENCIES:
        dependency_hash = digest(dependency.read_bytes())
        expected_hash = REFERENCE_DEPENDENCY_SHA256[dependency.name]
        if dependency_hash != expected_hash:
            failures.append(f"locked helper-module digest mismatch: {dependency.name}")
        dependency_records.append({"path": str(dependency.relative_to(ROOT)).replace("\\", "/"), "sha256": dependency_hash, "expected_sha256": expected_hash})
    reference_text = reference_bytes.decode("utf-8")
    declaration = "module UopInfoGen("
    if reference_text.count(declaration) != 1:
        failures.append("reference does not contain exactly one UopInfoGen module")
    renamed_reference = reference_text.replace(declaration, "module UopInfoGen_reference(", 1)

    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))["modules"]["UopInfoGen"]
    expected_ports = [
        (str(port["name"]), str(port["direction"]), int(str(port["width"]).strip("[]").split(":")[0]) - int(str(port["width"]).strip("[]").split(":")[1]) + 1 if ":" in str(port["width"]) else 1)
        for port in hierarchy["ports"]
    ]
    actual_ports = list(module.PORT_SPECS["UopInfoGen"])
    if expected_ports != actual_ports:
        failures.append("ordered ABI differs from locked hierarchy")

    rtl_first = module.build_verilog({"module": "UopInfoGen"}, {})
    rtl_second = module.build_verilog({"module": "UopInfoGen"}, {})
    deterministic = rtl_first == rtl_second
    if not deterministic:
        failures.append("same-name export is not deterministic")

    WORK.mkdir(parents=True, exist_ok=True)
    dut_path = WORK / "UopInfoGen_DUT.sv"
    ref_path = WORK / "UopInfoGen_reference.sv"
    dependency_paths = [WORK / dependency.name for dependency in REFERENCE_DEPENDENCIES]
    tb_path = WORK / "uopinfo_diff_tb.sv"
    dut_path.write_text(rtl_first, encoding="utf-8", newline="\n")
    ref_path.write_text(renamed_reference, encoding="utf-8", newline="\n")
    for dependency, destination in zip(REFERENCE_DEPENDENCIES, dependency_paths):
        destination.write_bytes(dependency.read_bytes())
    tb_path.write_text(make_testbench(expected_ports), encoding="utf-8", newline="\n")

    rtl_hash = digest(rtl_first.encode())
    obj_path = WORK / ("obj-" + rtl_hash[:12])
    wsl_dut = wsl_path(dut_path)
    wsl_ref = wsl_path(ref_path)
    wsl_dependencies = [wsl_path(path) for path in dependency_paths]
    wsl_tb = wsl_path(tb_path)
    wsl_obj = wsl_path(obj_path)
    prior_evidence = json.loads(EVIDENCE.read_text(encoding="utf-8")) if EVIDENCE.exists() else None
    prior_diff = prior_evidence.get("reference_differential", {}) if isinstance(prior_evidence, dict) else {}
    prior_locked = prior_evidence.get("locked_reference", {}) if isinstance(prior_evidence, dict) else {}
    can_reuse_diff = (
        isinstance(prior_evidence, dict)
        and prior_evidence.get("export", {}).get("sha256") == rtl_hash
        and prior_locked.get("xstop_sha256") == actual_xstop_hash
        and prior_locked.get("module_sha256") == reference_hash
        and prior_diff.get("status") == "PASS"
        and prior_diff.get("cases") == COMBINATIONAL_CASES + COMPLEX_CASES
    )
    if reuse_reference_diff and can_reuse_diff:
        compile_diff = prior_diff["compile"]
        execute_diff = prior_diff["run"]
    elif reuse_reference_diff:
        compile_diff = {"status": "NOT_REUSED", "reason": "prior differential source identities do not match"}
        execute_diff = {"status": "NOT_RUN", "reason": "prior differential source identities do not match"}
        failures.append("requested prior differential cannot be rebound to current sources")
    else:
        compile_diff = run_wsl(
            [
                "verilator", "--binary", "--timing", "-Wno-fatal",
                "--top-module", "uopinfo_diff_tb", "--Mdir", wsl_obj,
                wsl_dut, wsl_ref, *wsl_dependencies, wsl_tb,
            ]
        )
        if compile_diff["status"] == "PASS":
            execute_diff = run_wsl([f"{wsl_obj}/Vuopinfo_diff_tb"])
        else:
            execute_diff = {"status": "NOT_RUN", "reason": "Verilator compile failed"}
    if execute_diff.get("status") != "PASS":
        failures.append("exhaustive Verilator reference differential failed")

    export_path = WORK / "UopInfoGen.sv"
    export_path.write_text(rtl_first, encoding="utf-8", newline="\n")
    linux_export = wsl_path(export_path)
    verilator_lint = run_wsl(["verilator", "--lint-only", "-Wno-fatal", linux_export])
    yosys_script = (
        f'read_verilog -sv "{linux_export}"; '
        "hierarchy -check -top UopInfoGen; proc; stat; check"
    )
    yosys = run_wsl(["yosys", "-Q", "-p", yosys_script], require_yosys_top="UopInfoGen")
    if verilator_lint["status"] != "PASS":
        failures.append("Verilator lint failed")
    if yosys["status"] != "PASS":
        failures.append("Yosys check failed")

    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_CLOSURE_WAVE_UOPINFO",
        "batch_id": "V2-BACKEND-CLOSURE-WAVE-001",
        "member": "UopInfoGen",
        "build_path": str(TARGET.relative_to(ROOT)).replace("\\", "/"),
        "build_sha256": digest(TARGET.read_bytes()),
        "locked_reference": {
            "canonical_path": LOCKED_XSTOP,
            "xstop_sha256": actual_xstop_hash,
            "expected_xstop_sha256": LOCKED_XSTOP_SHA256,
            "module": "UopInfoGen",
            "module_sha256": reference_hash,
            "expected_module_sha256": REFERENCE_SHA256,
            "helper_modules": dependency_records,
        },
        "port_abi": {"locked": len(expected_ports), "emitted": len(actual_ports), "match": expected_ports == actual_ports},
        "export": {"status": "PASS" if deterministic else "FAIL", "bytes": len(rtl_first.encode()), "sha256": rtl_hash},
        "direct_test": direct,
        "reference_differential": {
            "status": execute_diff.get("status"),
            "candidate_rtl_source": "Amaranth build_verilog(UopInfoGen)",
            "reference_source": str(REFERENCE.relative_to(ROOT)).replace("\\", "/"),
            "reference_module_sha256": reference_hash,
            "case_dimensions": {
                "split": 64, "vlmul": 8, "vsew": 4, "vwidth": 8,
                "nf": 8, "vmvn": 8, "vlsr_vlsm_modes": 4,
                "complex_flags": 8,
            },
            "cases": COMBINATIONAL_CASES + COMPLEX_CASES,
            "reused_prior_execution": reuse_reference_diff and can_reuse_diff,
            "compile": compile_diff,
            "run": execute_diff,
        },
        "tool_gates": {"py_compile": "PASS", "pyright": pyright, "verilator_lint": verilator_lint, "yosys": yosys},
        "gates": {
            "DIRECT_TEST_PASS_BOUNDED": "PASS_BOUNDED",
            "V2_REFERENCE_MATCHED": "PASS_EXHAUSTIVE_COMBINATIONAL_DIFFERENTIAL" if execute_diff.get("status") == "PASS" else "STRICT_PENDING",
            "FORMAL": "PENDING_ROOT_SERIAL_RAIL",
            "PARENT_CLOSURE_MATCHED": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "DIRECT_TEST_PASS_BOUNDED" if not failures else "FAIL",
        "acceptance_eligible": False,
        "strict_delta": 0,
        "failures": failures,
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "member": "UopInfoGen", "differential": execute_diff.get("status"), "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
