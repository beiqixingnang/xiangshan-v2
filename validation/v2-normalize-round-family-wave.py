"""Audit and validate the frozen standalone CLZ/rounding module family."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import re
import shlex
import shutil
import subprocess
import sys
from bisect import bisect_right
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Dependency.Fpu.NormalizeRoundFamily-Hardware.py"
TEST = ROOT / "python/Program-System/System-Testing/Testing-Cpu/Testing-Cpu-Dependency.Fpu.NormalizeRoundFamily-Hardware.py"
DIRECT_RUNNER = ROOT / "validation/v2_direct_test_runner.py"
LOCKED_HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
HIERARCHY_COVERAGE = ROOT / "validation/v2-hierarchy-coverage.json"
COMPLETE_CLOSURE = ROOT / "validation/v2-complete-closure-inventory.json"
REFERENCE_DIR = ROOT / "validation/reference-sv"
SOURCE_ROOT = ROOT / "upstream/yunsuan/src/main/scala"
WORK = ROOT / "validation/.work/v2-normalize-round-family-wave"
EVIDENCE = ROOT / "validation/v2-normalize-round-family-wave-results.json"
CLZ_NAMES = ("CLZ", "CLZ_6", "CLZ_7", "CLZ_9", "CLZ_11", "CLZ_28", "CLZ_29", "CLZ_30", "CLZ_31")
ROUND_NAMES = ("RoundingUnit", "RoundingUnit_1", "RoundingUnit_2", "RoundingUnit_3",
               "RoundingUnit_4", "RoundingUnit_8", "RoundingUnit_9", "RoundingUnit_11")
MEMBERS = CLZ_NAMES + ROUND_NAMES
MODULE_PATTERN = re.compile(r"^module\s+([A-Za-z0-9_$]+)\b", re.M)
INSTANCE_PATTERN = re.compile(r"^\s*(CLZ(?:_\d+)?|RoundingUnit(?:_\d+)?)\s+([A-Za-z_$][\w$]*)\s*\(", re.M)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def width(token: str) -> int:
    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def run(command: list[str], timeout: int = 300) -> dict[str, Any]:
    try:
        result = subprocess.run(command, capture_output=True, check=False, timeout=timeout)
        output = (result.stdout + result.stderr).decode("utf-8", "replace")
        return {"status": "PASS" if result.returncode == 0 else "FAIL",
                "returncode": result.returncode, "output_tail": output[-1600:]}
    except subprocess.TimeoutExpired as error:
        return {"status": "TIMEOUT", "returncode": None, "output_tail": str(error)[:1600]}


def wsl_path(path: Path) -> str:
    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


def wsl(command: list[str], timeout: int = 300) -> dict[str, Any]:
    return run(["wsl.exe", "-e", "bash", "-lc", shlex.join(command)], timeout)


def member_uses() -> dict[str, list[dict[str, str | int]]]:
    uses: dict[str, list[dict[str, str | int]]] = {name: [] for name in MEMBERS}
    for path in REFERENCE_DIR.glob("*.sv"):
        text = path.read_text(encoding="utf-8", errors="replace")
        modules = list(MODULE_PATTERN.finditer(text))
        starts = [item.start() for item in modules]
        for match in INSTANCE_PATTERN.finditer(text):
            member, instance = match.groups()
            if member not in uses:
                continue
            module_index = bisect_right(starts, match.start()) - 1
            owner = modules[module_index].group(1) if module_index >= 0 else ""
            line = text.count("\n", 0, match.start()) + 1
            uses[member].append({"reference_file": path.name, "parent_module": owner,
                                 "instance": instance, "line": line})
    return uses


def tb_source(member: str, width: int, out_width: int, scalar_rounding: bool) -> str:
    if member in CLZ_NAMES:
        return f'''module normalize_round_tb;
  reg [{width - 1}:0] io_in;
  wire [{out_width - 1}:0] ref_io_out, dut_io_out;
  integer i, seed;
  {member} reference_i(.io_in(io_in), .io_out(ref_io_out));
  NormalizeRoundDut target_i(.io_in(io_in), .io_out(dut_io_out));
  task check;
    begin
      #1;
      if (ref_io_out !== dut_io_out) begin
        $display("MISMATCH member={member} in=%h ref=%h dut=%h", io_in, ref_io_out, dut_io_out);
        $fatal(1);
      end
    end
  endtask
  initial begin
    seed = 32'h2c61a74d;
    io_in = 0; check;
    io_in = {{{width}{{1'b1}}}}; check;
    for (i = 0; i < {width}; i = i + 1) begin
      io_in = {{{{({width - 1}){{1'b0}}}}, 1'b1}} << i;
      check;
    end
    for (i = 0; i < 512; i = i + 1) begin
      io_in = {{$random(seed), $random(seed)}};
      check;
    end
    $display("NORMALIZE_ROUND_DIFF_PASS member={member}");
    $finish;
  end
endmodule
'''

    outputs = ["io_inexact", "io_cout"] if scalar_rounding else ["io_inexact", "io_r_up"]
    output_ports = ", ".join(f".{name}(ref_{name})" for name in outputs)
    dut_ports = ", ".join(f".{name}(dut_{name})" for name in outputs)
    output_wires = "\n  ".join(f"wire ref_{name}, dut_{name};" for name in outputs)
    comparisons = " || ".join(f"ref_{name} !== dut_{name}" for name in outputs)
    print_values = ", ".join(f"ref_{name}, dut_{name}" for name in outputs)
    scalar_outputs = ""
    if scalar_rounding:
        scalar_outputs = f"wire [{width - 1}:0] ref_io_out, dut_io_out;"
        output_ports = f".io_out(ref_io_out), {output_ports}"
        dut_ports = f".io_out(dut_io_out), {dut_ports}"
        comparisons = f"(ref_io_out !== dut_io_out) || {comparisons}"
        print_values = f"ref_io_out, dut_io_out, {print_values}"
    return f'''module normalize_round_tb;
  reg [{width - 1}:0] io_in;
  reg io_roundIn, io_stickyIn, io_signIn;
  reg [2:0] io_rm;
  {scalar_outputs}
  {output_wires}
  integer mode, flags, sample, seed;
  {member} reference_i(.io_in(io_in), .io_roundIn(io_roundIn), .io_stickyIn(io_stickyIn), .io_signIn(io_signIn), .io_rm(io_rm), {output_ports});
  NormalizeRoundDut target_i(.io_in(io_in), .io_roundIn(io_roundIn), .io_stickyIn(io_stickyIn), .io_signIn(io_signIn), .io_rm(io_rm), {dut_ports});
  task check;
    begin
      #1;
      if ({comparisons}) begin
        $display("MISMATCH member={member} in=%h rm=%h round=%b sticky=%b sign=%b outputs={print_values}", io_in, io_rm, io_roundIn, io_stickyIn, io_signIn);
        $fatal(1);
      end
    end
  endtask
  initial begin
    seed = 32'h3e7162a9;
    for (mode = 0; mode < 8; mode = mode + 1)
      for (flags = 0; flags < 8; flags = flags + 1)
        for (sample = 0; sample < 6; sample = sample + 1) begin
          io_rm = mode;
          io_roundIn = flags[0];
          io_stickyIn = flags[1];
          io_signIn = flags[2];
          case (sample)
            0: io_in = 0;
            1: io_in = 1;
            2: io_in = {{{width}{{1'b1}}}};
            3: io_in = {{{width}{{1'b1}}}} - 1'b1;
            4: io_in = {{{width}{{1'b0}}}} | (1'b1 << ({width} - 1));
            default: io_in = {{$random(seed), $random(seed)}};
          endcase
          check;
        end
    $display("NORMALIZE_ROUND_DIFF_PASS member={member}");
    $finish;
  end
endmodule
'''


def main() -> int:
    sys.path.insert(0, str(ROOT / "validation"))
    from v2_strict_family_rail import declared_ports

    WORK.mkdir(parents=True, exist_ok=True)
    build_spec = importlib.util.spec_from_file_location("normalize_round_wave_build", BUILD)
    if build_spec is None or build_spec.loader is None:
        raise RuntimeError(BUILD)
    build = importlib.util.module_from_spec(build_spec)
    sys.modules[build_spec.name] = build
    build_spec.loader.exec_module(build)

    locked_hierarchy = json.loads(LOCKED_HIERARCHY.read_text(encoding="utf-8"))
    locked_modules = locked_hierarchy["modules"]
    frozen_names = tuple(sorted(
        (name for name in locked_modules
         if re.fullmatch(r"CLZ(?:_\d+)?|RoundingUnit(?:_\d+)?", name)),
        key=lambda name: ((0 if name.startswith("CLZ") else 1),
                          -1 if "_" not in name else int(name.rsplit("_", 1)[1])),
    ))
    failures: list[str] = []
    if frozen_names != MEMBERS:
        failures.append("complete_locked_member_set")
    if tuple(build.COVERED_MODULES) != MEMBERS or tuple(build.IMPLEMENTED_MEMBERS) != MEMBERS:
        failures.append("build_member_set")

    coverage_rows = json.loads(HIERARCHY_COVERAGE.read_text(encoding="utf-8"))["rows"]
    coverage = {row["module"]: row for row in coverage_rows if row.get("module") in MEMBERS}
    inventory = json.loads(COMPLETE_CLOSURE.read_text(encoding="utf-8"))
    inventory_modules = {row["module"]: row for row in inventory["modules"] if row.get("module") in MEMBERS}
    if set(inventory_modules) != set(MEMBERS) or any(not inventory_modules[name].get("reachable_from_XSTop") for name in MEMBERS):
        failures.append("reachable_module_set")
    if set(coverage) != set(MEMBERS):
        failures.append("hierarchy_coverage_rows")

    source_files: dict[str, Path] = {}
    members: dict[str, Any] = {}
    for name in MEMBERS:
        row = locked_modules[name]
        ports = row["ports"]
        source_records = []
        for source in row.get("scala_sources", []):
            rel = source.split("yunsuan/src/main/scala/", 1)[1].split(":", 1)[0]
            path = SOURCE_ROOT / rel
            source_files[rel] = path
            source_records.append({"source": source, "sha256": sha256(path)})
        ref_path = REFERENCE_DIR / f"{name}.sv"
        hierarchy_ports = {(p["name"], p["direction"], width(str(p.get("width", "")))) for p in ports}
        port_names = {p["name"].lower() for p in ports}
        members[name] = {
            "reachable_from_XSTop": inventory_modules[name]["reachable_from_XSTop"],
            "closure_status_at_freeze": inventory_modules[name]["status"],
            "family_subjects": coverage[name].get("family_subjects", []),
            "children": inventory_modules[name].get("children", []),
            "ports": [{"name": p["name"], "direction": p["direction"],
                       "width": width(str(p.get("width", "")))} for p in ports],
            "clock_or_reset_ports": sorted(name for name in port_names if "clock" in name or "reset" in name),
            "scala_sources": source_records,
            "reference_file": ref_path.name,
            "reference_sha256": sha256(ref_path),
            "locked_module_port_count": len(hierarchy_ports),
        }

    instances = member_uses()
    if any(not instances[name] for name in MEMBERS):
        failures.append("locked_reference_instance_audit")
    for name in MEMBERS:
        members[name]["locked_instances"] = instances[name]

    py_compile.compile(str(BUILD), doraise=True)
    py_compile.compile(str(TEST), doraise=True)
    pyright = shutil.which("pyright")
    pyright_result = run(["powershell.exe", "-NoProfile", "-Command", f"pyright '{BUILD}'"]) if pyright else {
        "status": "UNAVAILABLE", "returncode": None, "output_tail": "pyright not found"}
    if pyright_result["status"] != "PASS":
        failures.append("pyright")
    direct = run([sys.executable, "-B", str(DIRECT_RUNNER), "--test",
                  str(TEST.relative_to(ROOT)), "--minimum-tests", "3"], timeout=180)
    test_match = re.search(r"Ran\s+(\d+) tests?", str(direct.get("output_tail", "")))
    direct_tests = int(test_match.group(1)) if test_match else 0
    if direct["status"] != "PASS" or direct_tests < 3:
        failures.append("direct_test")

    member_gates: dict[str, Any] = {}
    outputs: dict[str, Path] = {}
    for name in MEMBERS:
        rtl = build.build_verilog({"module": name}, {})
        rtl_again = build.build_verilog({"module": name}, {})
        rtl_path = WORK / f"{name}.sv"
        rtl_path.write_text(rtl, encoding="utf-8", newline="\n")
        outputs[name] = rtl_path
        expected = {
            (p["name"], p["direction"], width(str(p.get("width", ""))))
            for p in locked_modules[name]["ports"]
        }
        declared = set(build.PORT_SPECS[name])
        abi_exact = declared == expected and declared_ports(rtl, name) == {
            port: (direction, bits) for port, direction, bits in expected
        }
        deterministic = rtl == rtl_again
        linux_rtl = wsl_path(rtl_path)
        verilator = wsl(["verilator", "--lint-only", "-Wno-fatal", linux_rtl])
        yosys = wsl(["yosys", "-Q", "-p", f"read_verilog -sv {shlex.quote(linux_rtl)}; proc; check"])
        tb_path = WORK / f"{name}.tb.sv"
        in_width = build.CLZ_CONFIG[name][0] if name in build.CLZ_CONFIG else build.ROUNDING_CONFIG[name][0]
        out_width = next(p[2] for p in build.PORT_SPECS[name] if p[0] == "io_out") if name in CLZ_NAMES or name in ("RoundingUnit", "RoundingUnit_1", "RoundingUnit_2") else 1
        vector_surface = name in build.ROUNDING_CONFIG and build.ROUNDING_CONFIG[name][1]
        tb_path.write_text(tb_source(name, in_width, out_width,
                                     name in build.ROUNDING_CONFIG and not vector_surface),
                           encoding="utf-8", newline="\n")
        dut_path = WORK / f"{name}.dut.sv"
        dut_module_name = f"NormalizeRoundDut"
        dut_path.write_text(rtl.replace(f"module {name}(", f"module {dut_module_name}(", 1),
                            encoding="utf-8", newline="\n")
        diff = run_verilator_differential(name, ref_path=REFERENCE_DIR / f"{name}.sv",
                                          dut_path=dut_path, tb_path=tb_path)
        member_gates[name] = {
            "abi_exact": abi_exact,
            "deterministic": deterministic,
            "rtl_bytes": len(rtl.encode("utf-8")),
            "rtl_sha256": hashlib.sha256(rtl.encode("utf-8")).hexdigest(),
            "verilator_lint": verilator,
            "yosys_check": yosys,
            "locked_executable_diff": diff,
            "diff_testbench_sha256": sha256(tb_path),
        }
        if not abi_exact:
            failures.append(f"abi:{name}")
        if not deterministic:
            failures.append(f"determinism:{name}")
        if verilator["status"] != "PASS":
            failures.append(f"verilator:{name}")
        if yosys["status"] != "PASS":
            failures.append(f"yosys:{name}")
        if diff["status"] != "PASS" or f"NORMALIZE_ROUND_DIFF_PASS member={name}" not in str(diff.get("output_tail", "")):
            failures.append(f"locked_diff:{name}")

    scalar_build = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Dependency.YunSuan.Scalar-Hardware.py"
    vector_build = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Dependency.YunSuan.Vector-Hardware.py"
    base_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                 capture_output=True, check=False).stdout.decode().strip()
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FPU_NORMALIZE_ROUND_FAMILY_WAVE",
        "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "formal": "NOT_RUN_BY_REQUEST",
        "base_commit": base_commit,
        "candidate_hashes": {
            "build_sha256": sha256(BUILD),
            "direct_test_sha256": sha256(TEST),
            "direct_runner_sha256": sha256(DIRECT_RUNNER),
            "validator_sha256": sha256(Path(__file__)),
        },
        "frozen_family": {
            "locked_module_count": locked_hierarchy["module_count"],
            "clz_members": list(CLZ_NAMES),
            "rounding_members": list(ROUND_NAMES),
            "members": members,
            "scala_source_hashes": {rel: sha256(path) for rel, path in source_files.items()},
            "hierarchy_sha256": sha256(LOCKED_HIERARCHY),
            "complete_closure_inventory_sha256": sha256(COMPLETE_CLOSURE),
            "hierarchy_coverage_sha256": sha256(HIERARCHY_COVERAGE),
        },
        "existing_generic_family_overlap": {
            "scalar_build_sha256": sha256(scalar_build),
            "scalar_build": "provides generic CLZ and scalar-rounding behavior APIs; its selected standalone mode does not emit all frozen exact-name ABI variants",
            "vector_build_sha256": sha256(vector_build),
            "vector_build": "provides VCLZ instruction behavior but not independent CLZ_n/RoundingUnit_n ABI variants",
        },
        "tool_gates": {
            "PY_COMPILE": "PASS",
            "PYRIGHT": pyright_result,
            "DIRECT_TEST": {**direct, "tests_run": direct_tests},
            "ALL_MEMBER_ABI_DETERMINISTIC_VERILATOR_YOSYS_LOCKED_DIFF": member_gates,
        },
        "failures": failures,
        "remaining": [
            "SAT/formal and negative controls remain for the serialized coordinator rail.",
            "Parent-level closure and license review remain pending.",
        ],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "members": len(member_gates),
                      "direct_tests": direct_tests, "failures": failures}))
    return 0 if not failures else 1


def run_verilator_differential(name: str, ref_path: Path, dut_path: Path,
                               tb_path: Path) -> dict[str, Any]:
    obj = f"/tmp/v2_normalize_round_{name}"
    log_path = WORK / f"{name}.diff-build.log"
    linux_inputs = [wsl_path(path) for path in (ref_path, dut_path, tb_path)]
    linux_log = wsl_path(log_path)
    command = ["verilator", "--binary", "-Wno-fatal", "--top-module", "normalize_round_tb",
               "-Mdir", obj, *linux_inputs]
    shell = f"{shlex.join(command)} > {shlex.quote(linux_log)} 2>&1 && {shlex.quote(obj + '/Vnormalize_round_tb')}"
    return run(["wsl.exe", "-e", "bash", "-lc", shell], timeout=600)


if __name__ == "__main__":
    raise SystemExit(main())
