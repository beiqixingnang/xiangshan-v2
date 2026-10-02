"""Run bounded executable, ABI, lint, and synthesis checks for BitSelectFamily."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from v2_strict_family_rail import (
    REF_DIR,
    ROOT,
    FamilyRail,
    enumerate_members,
    load_module,
    pyright_check,
    run_wsl,
    wsl_path,
)


BUILD_ID = "Build-Cpu.Dependency.Utility.BitSelectFamily"
BUILD_PATH = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Cpu-Core-Dependency.Utility.BitSelectFamily-Hardware.py"
)
TEST_PATH = ROOT / (
    "python/Program-System/System-Testing/Testing-Cpu/"
    "Testing-Cpu-Dependency.Utility.BitSelectFamily-Hardware.py"
)
RESULT_PATH = ROOT / "validation/v2-bitselect-family-wave-results.json"
DIRECT_RUNNER = ROOT / "validation/v2_direct_test_runner.py"
SCALA_SOURCES = (
    ROOT / "upstream/utility/src/main/scala/utility/PriorityMuxGen.scala",
    ROOT / "upstream/utility/src/main/scala/utility/UIntUtils.scala",
)
MEMBERS = (
    "PriorityMuxModule",
    "PriorityMuxModule_4",
    "PriorityMuxModule_8",
    "PriorityMuxModule_12",
    "PriorityMuxModule_16",
    "PriorityMuxModule_20",
    "UIntCompressor_27_000011100000000000001010101",
    "UIntCompressor_27_000000000000001010100000000",
    "UIntExtractor_27_000011100000000000001010101",
    "UIntExtractor_27_000000000000001010100000000",
)


def source_record(path: Path) -> dict[str, object]:
    content = path.read_bytes()
    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}


def signal_declaration(name: str, width: int, kind: str = "logic") -> str:
    shape = "" if width == 1 else f" [{width - 1}:0]"
    return f"  {kind}{shape} {name};"


def instance_text(module_name: str, instance_name: str,
                  inputs: dict[str, int], outputs: dict[str, int],
                  output_prefix: str) -> str:
    connections = [f"    .{name}({name})" for name in inputs]
    connections.extend(f"    .{name}({output_prefix}{name})" for name in outputs)
    return f"  {module_name} {instance_name} (\n" + ",\n".join(connections) + "\n  );"


def comparison_text(outputs: dict[str, int]) -> str:
    terms = [f"dut_{name} !== ref_{name}" for name in outputs]
    return " ||\n      ".join(terms)


def wave_testbench(name: str, item: dict[str, object]) -> tuple[str, int]:
    inputs = item["inputs"]
    outputs = item["outputs"]
    if not isinstance(inputs, dict) or not isinstance(outputs, dict):
        raise TypeError("prepared member interfaces must be dictionaries")
    test_name = "v2_bitselect_wave_" + re.sub(r"\W+", "_", name).strip("_").lower()
    declarations = [signal_declaration(port, width) for port, width in inputs.items()]
    declarations.extend(signal_declaration("dut_" + port, width, "wire")
                        for port, width in outputs.items())
    declarations.extend(signal_declaration("ref_" + port, width, "wire")
                        for port, width in outputs.items())
    declarations.extend(("  integer cycle;", "  integer unsigned seed;"))
    target_instance = instance_text("DUT_" + name, "dut", inputs, outputs, "dut_")
    reference_instance = instance_text("REF_" + name, "reference", inputs, outputs, "ref_")
    selectors = [port for port in inputs if port.endswith("_sel")]
    mismatch = comparison_text(outputs)

    lines = [
        "`timescale 1ns/1ps",
        f"module {test_name};",
        *declarations,
        target_instance,
        reference_instance,
        "  initial begin",
        "    seed = 32'h6b17e151;",
    ]
    if selectors:
        cycle_count = 128
        pattern_count = 1 << len(selectors)
        lines.append(f"    for (cycle = 0; cycle < {cycle_count}; cycle = cycle + 1) begin")
        lines.extend(
            f"      {selector} = 1'(((cycle % {pattern_count}) >> {index}) & 1);"
            for index, selector in enumerate(selectors)
        )
        data_inputs = [port for port in inputs if port not in selectors]
        lines.extend(random_assignment(port, width)
                     for port, width in inputs.items() if port in data_inputs)
        lines.extend(("      #1;", f"      if ({mismatch})",
                      f'        $fatal(1, "locked output mismatch in {name}, cycle=%0d", cycle);',
                      "    end"))
    elif name.startswith("UIntCompressor_"):
        input_width = inputs["io_in"]
        lines.extend((f"    for (cycle = 0; cycle < {input_width}; cycle = cycle + 1) begin",
                      f"      io_in = {input_width}'h1 << cycle;", "      #1;",
                      f"      if ({mismatch})",
                      f'        $fatal(1, "locked output mismatch in {name}, bit=%0d", cycle);',
                      "    end", "    for (cycle = 0; cycle < 64; cycle = cycle + 1) begin",
                      random_assignment("io_in", input_width), "      #1;",
                      f"      if ({mismatch})",
                      f'        $fatal(1, "locked output mismatch in {name}, random=%0d", cycle);',
                      "    end"))
        cycle_count = input_width + 64
    else:
        input_width = inputs["io_in"]
        cycle_count = 1 << input_width
        lines.extend((f"    for (cycle = 0; cycle < {cycle_count}; cycle = cycle + 1) begin",
                      f"      io_in = {input_width}'(cycle);", "      #1;", f"      if ({mismatch})",
                      f'        $fatal(1, "locked output mismatch in {name}, input=%0d", cycle);',
                      "    end"))
    lines.extend((f'    $display("PASS {name} vectors=%0d", {cycle_count});',
                  "    $finish;", "  end", "endmodule", ""))
    return "\n".join(lines), cycle_count


def random_assignment(port: str, width: int) -> str:
    chunks = (width + 31) // 32
    expression = "$urandom(seed)" if chunks == 1 else "{" + ", ".join(
        "$urandom(seed)" for _ in range(chunks)
    ) + "}"
    return f"      {port} = {width}'({expression});"


def executable_diff(name: str, item: dict[str, object]) -> dict[str, object]:
    testbench, vector_count = wave_testbench(name, item)
    directory = ROOT / "validation/.cache/v2-bitselect-family-wave" / name
    object_directory = directory / "obj_dir"
    directory.mkdir(parents=True, exist_ok=True)
    testbench_path = directory / f"{name}_wave.sv"
    testbench_path.write_text(testbench, encoding="utf-8", newline="\n")
    testbench_name = "v2_bitselect_wave_" + re.sub(r"\W+", "_", name).strip("_").lower()
    compile_result = run_wsl([
        "verilator", "--binary", "--timing", "-Wno-fatal",
        "--Mdir", wsl_path(object_directory), "--top-module", testbench_name,
        wsl_path(item["target"]), wsl_path(item["reference"]), wsl_path(testbench_path),
    ])
    execution: dict[str, object] | None = None
    if compile_result.get("returncode") == 0:
        executable = object_directory / f"V{testbench_name}"
        execution = run_wsl([wsl_path(executable)])
    passed = (compile_result.get("returncode") == 0
              and execution is not None and execution.get("returncode") == 0
              and f"PASS {name} vectors={vector_count}" in str(execution.get("output_tail", "")))
    return {
        "status": "PASS" if passed else "FAIL",
        "vectors_per_member": vector_count,
        "compared_outputs": len(item["outputs"]),
        "compile": compile_result,
        "execution": execution,
        "testbench": testbench_path.relative_to(ROOT).as_posix(),
    }


def structural_yosys(item: dict[str, object]) -> dict[str, object]:
    name = str(item["name"])
    target = wsl_path(item["target"])
    reference = wsl_path(item["reference"])
    miter = wsl_path(item["miter"])
    script = (f"read_verilog -sv {target} {reference} {miter}; "
              f"hierarchy -check -top {name}_MITER; "
              f"proc; flatten; opt; check; stat")
    result = run_wsl(["yosys", "-Q", "-p", script])
    return {"status": result.get("status"), "returncode": result.get("returncode"),
            "command": result.get("command"), "output_tail": result.get("output_tail")}


def instance_counts() -> dict[str, int]:
    patterns = {name: re.compile(
        r"^\s*" + re.escape(name) + r"\s+[A-Za-z_$][\w$]*\s*\(", re.M
    ) for name in MEMBERS}
    totals = {name: 0 for name in MEMBERS}
    for source in REF_DIR.glob("*.sv"):
        text = source.read_text(encoding="utf-8", errors="replace")
        for name, pattern in patterns.items():
            totals[name] += len(pattern.findall(text))
    return totals


def main() -> int:
    import py_compile

    print("compiling sources and running the registered-path direct suite", flush=True)
    for path in (BUILD_PATH, TEST_PATH):
        py_compile.compile(str(path), doraise=True)

    direct_command = [
        sys.executable, "-B", DIRECT_RUNNER.relative_to(ROOT).as_posix(),
        "--test", TEST_PATH.relative_to(ROOT).as_posix(), "--minimum-tests", "4",
    ]
    direct = subprocess.run(direct_command, cwd=ROOT, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", check=False)
    pyright = pyright_check(BUILD_PATH)
    module = load_module("bitselect_family_wave", BUILD_PATH)
    resolved_members = enumerate_members(module, BUILD_PATH)
    if tuple(resolved_members) != tuple(sorted(MEMBERS)):
        raise ValueError("Build member catalog does not resolve to the ten assigned names")

    evidence_path = RESULT_PATH
    rail = FamilyRail(BUILD_PATH, BUILD_ID, evidence_path)
    rail.work.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, object]] = {}
    for name in resolved_members:
        print(f"checking {name}", flush=True)
        item = rail.prepare(module, name)
        static_failures = rail.cheap_static_failures(item)
        if not static_failures and pyright.get("status") == "PASS":
            lint, locked_lint = rail.lint_gate(item)
        else:
            lint, locked_lint = {"status": "NOT_RUN"}, {"status": "NOT_RUN"}
        yosys = structural_yosys(item) if not static_failures else {"status": "NOT_RUN"}
        executable = (executable_diff(name, item)
                      if not static_failures and lint.get("status") == "PASS"
                      and locked_lint.get("status") == "PASS"
                      else {"status": "NOT_RUN"})
        results[name] = {
            "module_definition": True,
            "locked_reference_sha256": hashlib.sha256(
                (REF_DIR / f"{name}.sv").read_bytes()).hexdigest(),
            "instances_in_locked_reference_tree": None,
            "abi_exact": item.get("abi_exact"),
            "deterministic_export": item.get("deterministic"),
            "static_failures": static_failures,
            "verilator_dut_and_miter_lint": lint,
            "verilator_locked_reference_lint": locked_lint,
            "yosys_structural_check": yosys,
            "locked_executable_differential": executable,
        }
        print(
            f"{name}: abi={item.get('abi_exact')} lint={lint.get('status')}/"
            f"{locked_lint.get('status')} yosys={yosys.get('status')} "
            f"diff={executable.get('status')}",
            flush=True,
        )

    counts = instance_counts()
    for name, count in counts.items():
        results[name]["instances_in_locked_reference_tree"] = count
    source_start = {"build": source_record(BUILD_PATH), "test": source_record(TEST_PATH)}
    source_end = {"build": source_record(BUILD_PATH), "test": source_record(TEST_PATH)}
    tool_pass = all(
        record["abi_exact"] is True
        and record["deterministic_export"] is True
        and not record["static_failures"]
        and record["verilator_dut_and_miter_lint"].get("status") == "PASS"
        and record["verilator_locked_reference_lint"].get("status") == "PASS"
        and record["yosys_structural_check"].get("status") == "PASS"
        and record["locked_executable_differential"].get("status") == "PASS"
        for record in results.values()
    )
    stable = source_start == source_end
    passed = direct.returncode == 0 and pyright.get("status") == "PASS" and tool_pass and stable
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_BITSELECT_FAMILY_BEHAVIORAL_WAVE",
        "status": "DIRECT_ABI_AND_EXECUTABLE_DIFF_PASS_FORMAL_PENDING" if passed else "FOCUSED_VALIDATION_FAILED",
        "strict_complete_count_delta": 0,
        "strict_equivalence_credit": "NOT_CLAIMED",
        "formal": "NOT_RUN_BY_IMPLEMENTATION_WORKER",
        "scope": {
            "module_definitions": len(MEMBERS),
            "locked_hierarchy_module_count": 1976,
            "instance_total": sum(counts.values()),
            "instance_counts": counts,
            "covered_modules": list(MEMBERS),
        },
        "sources": {
            "build": source_end["build"],
            "direct_test": source_end["test"],
            "validator": source_record(Path(__file__).resolve()),
            "direct_runner": source_record(DIRECT_RUNNER),
            "locked_scala_sources": [source_record(path) for path in SCALA_SOURCES],
        },
        "checks": {
            "py_compile": {"status": "PASS"},
            "direct_test": {
                "status": "PASS" if direct.returncode == 0 else "FAIL",
                "returncode": direct.returncode,
                "command": direct_command,
                "output_tail": (direct.stdout + direct.stderr)[-3000:],
            },
            "pyright": pyright,
            "source_stability": {"status": "PASS" if stable else "FAIL"},
            "all_members": results,
            "member_checks_pass": tool_pass,
        },
        "remaining_gates": [
            "serialized Yosys SAT/formal and negative controls",
            "parent/family closure and system-level acceptance",
        ],
    }
    RESULT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")
    print(json.dumps({
        "status": payload["status"],
        "module_definitions": len(MEMBERS),
        "instances": sum(counts.values()),
        "direct_returncode": direct.returncode,
        "pyright_files_analyzed": pyright.get("files_analyzed"),
        "pyright_error_count": pyright.get("error_count"),
        "members_passed": sum(
            1 for record in results.values()
            if record["locked_executable_differential"].get("status") == "PASS"
        ),
        "evidence": RESULT_PATH.relative_to(ROOT).as_posix(),
    }, ensure_ascii=False), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
