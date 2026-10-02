"""Validate the complete V2 utility delay family against locked XSTop RTL.
将 V2 实用延迟族与锁定 XSTop RTL 做完整验证。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


# =============================================================================
# Module Contract
# =============================================================================
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Cpu-Core-Dependency.Utility.DelayFamily-Hardware.py"
)
DIRECT_TEST = ROOT / (
    "python/Program-System/System-Testing/Testing-Cpu/"
    "Testing-Cpu-Dependency.Utility.DelayFamily-Hardware.py"
)
DIRECT_RUNNER = ROOT / "validation/v2_direct_test_runner.py"
LOCKED_XSTOP = Path(
    r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv"
)
LOCKED_HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
WORK_ROOT = ROOT / "validation/.work/v2-utility-delay-wave"
EVIDENCE = ROOT / "validation/v2-utility-delay-wave-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
LOCKED_BYTES = 228590583
EXPECTED_COUNTS = {"plain": 18, "valid": 14, "enabled": 8, "pipe": 8}


# =============================================================================
# Configuration
# =============================================================================
def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def digest_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def port_width(port: dict[str, Any]) -> int:
    text = str(port.get("width", ""))
    if not text:
        return 1
    left, right = (int(value) for value in text[1:-1].split(":"))
    return abs(left - right) + 1


def run_process(command: list[str], *, cwd: Path | None = None) -> dict[str, Any]:
    completed = subprocess.run(command, capture_output=True, check=False,
                               cwd=str(cwd) if cwd else None)
    stdout = completed.stdout.decode("utf-8", "replace")
    stderr = completed.stderr.decode("utf-8", "replace")
    output = stdout + stderr
    return {
        "command": command,
        "returncode": completed.returncode,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "output_tail": output[-2400:],
        "output_sha256": digest_bytes(output.encode("utf-8", "replace")),
    }


def wsl_path(path: Path) -> str:
    completed = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                               capture_output=True, check=False)
    if completed.returncode:
        raise RuntimeError(completed.stderr.decode("utf-8", "replace"))
    return completed.stdout.decode("utf-8", "replace").strip()


def run_wsl(command: list[str]) -> dict[str, Any]:
    rendered = " ".join(shlex.quote(value) for value in command)
    return run_process(["wsl.exe", "-e", "bash", "-lc", rendered])


def pyright_command() -> list[str]:
    node = shutil.which("node.exe") or shutil.which("node")
    if node is None:
        raise FileNotFoundError("Node.js is required to invoke the installed Pyright package")
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        shim = Path(entry) / "pyright.ps1"
        script = shim.parent / "node_modules/pyright/index.js"
        if shim.is_file() and script.is_file():
            return [node, str(script), str(TARGET), str(DIRECT_TEST)]
    raise FileNotFoundError("could not locate the installed Pyright package beside pyright.ps1")


def load_target() -> Any:
    spec = importlib.util.spec_from_file_location("v2_utility_delay_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# =============================================================================
# Implementation
# =============================================================================
def extract_locked_modules(path: Path, names: tuple[str, ...],
                           hierarchy: dict[str, Any]) -> tuple[dict[str, bytes], str]:
    starts = {
        re.compile(rb"^module\s+" + re.escape(name.encode("ascii")) + rb"\s*\("): name
        for name in names
    }
    captured: dict[str, bytearray] = {}
    spans: dict[str, tuple[int, int]] = {}
    source_hash = hashlib.sha256()
    active_name: str | None = None
    active_start = 0
    with path.open("rb") as stream:
        for line_number, line in enumerate(stream, 1):
            source_hash.update(line)
            stripped = line.lstrip()
            if active_name is None:
                for pattern, candidate in starts.items():
                    if pattern.match(stripped):
                        active_name = candidate
                        active_start = line_number
                        captured[candidate] = bytearray(line)
                        break
                continue
            captured[active_name].extend(line)
            if stripped.startswith(b"endmodule"):
                spans[active_name] = (active_start, line_number)
                active_name = None
    if active_name is not None:
        raise RuntimeError(f"unterminated locked module: {active_name}")
    missing = set(names) - set(captured)
    if missing:
        raise RuntimeError(f"locked modules missing: {sorted(missing)}")
    for name in names:
        if tuple(hierarchy[name][key] for key in ("start_line", "end_line")) != spans[name]:
            raise RuntimeError(f"locked line span differs from hierarchy for {name}")
    return {name: bytes(captured[name]) for name in names}, source_hash.hexdigest()


def rename_module(payload: bytes, old_name: str, new_name: str) -> bytes:
    pattern = re.compile(rb"(?m)^module\s+" + re.escape(old_name.encode("ascii")) + rb"\s*\(")
    changed, count = pattern.subn(b"module " + new_name.encode("ascii") + b"(", payload, count=1)
    if count != 1:
        raise RuntimeError(f"could not rename module declaration: {old_name}")
    return changed


def declaration(kind: str, name: str, width: int) -> str:
    shape = "" if width == 1 else f" [{width - 1}:0]"
    return f"  {kind}{shape} {name};"


def input_pattern(name: str, width: int, member_index: int,
                  port_index: int, stages: int) -> list[str]:
    if name in ("clock", "reset"):
        return []
    if name in ("io_in_valid", "io_enq_valid"):
        return [f"      {name} = (cycle < {stages + 2}) ? 1'b1 : "
                f"(((cycle + {member_index}) % 5) != 0);"]
    if name.startswith("io_flush_"):
        return [f"      {name} = (cycle < {stages + 2}) ? 1'b0 : "
                f"(((cycle * 3 + {member_index} + {port_index}) % 7) == 0);"]
    if width == 1:
        return [f"      {name} = ((cycle * 5 + {member_index} * 3 + {port_index}) % 2);" ]
    return [
        f"      for (bit_index = 0; bit_index < {width}; bit_index = bit_index + 1)"
        f" {name}[bit_index] = (((cycle * 11 + {member_index} * 7 + {port_index} * 5"
        f" + bit_index * 3) % 23) < 11);"
    ]


def build_miter(module: Any, hierarchy: dict[str, Any],
                target_names: dict[str, str], reference_names: dict[str, str],
                cycles: int) -> tuple[str, dict[str, Any]]:
    declarations: list[str] = [
        "module DelayWaveMiter;",
        "  logic clock;",
        "  logic reset;",
        "  integer cycle;",
        "  integer bit_index;",
    ]
    instances: list[str] = []
    stimulus: list[str] = []
    checks: list[str] = []
    member_rows: dict[str, Any] = {}

    for member_index, member_name in enumerate(module.MEMBER_NAMES):
        configuration = module.family_configuration(member_name)
        record = hierarchy[member_name]
        member_outputs = []
        input_connections: list[str] = []
        output_connections_target: list[str] = []
        output_connections_reference: list[str] = []
        data_input_index = 0
        for port_index, port in enumerate(record["ports"]):
            name = port["name"]
            width = port_width(port)
            if port["direction"] == "input":
                if name in ("clock", "reset"):
                    signal_name = name
                else:
                    signal_name = f"m{member_index}_i{port_index}"
                    declarations.append(declaration("logic", signal_name, width))
                    stimulus.extend(input_pattern(name, width, member_index,
                                                  data_input_index, configuration.stages))
                    # Use the unique miter signal as the LHS of each generated
                    # assignment while keeping the locked port name in maps.
                    if stimulus:
                        stimulus[-1] = stimulus[-1].replace(name, signal_name)
                    data_input_index += 1
                input_connections.append(f".{name}({signal_name})")
            else:
                dut_signal = f"m{member_index}_d{port_index}"
                ref_signal = f"m{member_index}_r{port_index}"
                declarations.extend((declaration("wire", dut_signal, width),
                                     declaration("wire", ref_signal, width)))
                output_connections_target.append(f".{name}({dut_signal})")
                output_connections_reference.append(f".{name}({ref_signal})")
                member_outputs.append((name, dut_signal, ref_signal, width))
        instances.append(
            f"  {target_names[member_name]} dut_{member_index} ("
            + ", ".join(input_connections + output_connections_target) + ");"
        )
        instances.append(
            f"  {reference_names[member_name]} ref_{member_index} ("
            + ", ".join(input_connections + output_connections_reference) + ");"
        )
        warm = 0 if configuration.mode == "enabled" else max(0, configuration.stages - 1)
        compared = 0
        for output_name, dut_signal, ref_signal, width in member_outputs:
            if output_name == configuration.valid_output_name:
                checks.append(
                    f"      if ({dut_signal} !== {ref_signal}) $fatal(1, \"{member_name} {output_name} cycle=%0d\", cycle);"
                )
                compared += width * cycles
            else:
                checks.append(
                    f"      if (cycle >= {warm} && {dut_signal} !== {ref_signal})"
                    f" $fatal(1, \"{member_name} {output_name} cycle=%0d\", cycle);"
                )
                compared += width * (cycles - warm)
        member_rows[member_name] = {
            "mode": configuration.mode,
            "stages": configuration.stages,
            "startup_uninitialized_cycles": warm,
            "post_startup_output_policy": "all public outputs compared every cycle",
            "compared_public_output_bits": compared,
        }

    initializer = [
        "  initial begin",
        "    clock = 1'b0;",
        "    reset = 1'b1;",
    ]
    initializer.extend((
        "    #2;",
        "    reset = 1'b0;",
        f"    for (cycle = 0; cycle < {cycles}; cycle = cycle + 1) begin",
        "      clock = 1'b0;",
    ))
    initializer.extend(stimulus)
    initializer.extend(("      #1;", "      clock = 1'b1;", "      #1;"))
    initializer.extend(checks)
    initializer.extend((
        "      clock = 1'b0;",
        "      #1;",
        "    end",
        f"    $display(\"DELAY_FAMILY_LOCKED_DIFF_PASS {len(module.MEMBER_NAMES)}\");",
        "    $finish;",
        "  end",
        "endmodule",
    ))
    return "\n".join(declarations + instances + initializer) + "\n", member_rows


def main() -> int:
    module = load_target()
    hierarchy = json.loads(LOCKED_HIERARCHY.read_text(encoding="utf-8"))["modules"]
    failures: list[str] = []

    compile_results = []
    for path in (TARGET, DIRECT_TEST):
        result = run_process([sys.executable, "-B", "-m", "py_compile", str(path)])
        compile_results.append({"path": path.relative_to(ROOT).as_posix(), **result})
        if result["status"] != "PASS":
            failures.append(f"py_compile: {path.name}")
    pyright = run_process(pyright_command())
    if pyright["status"] != "PASS":
        failures.append("Pyright")

    direct = run_process([
        sys.executable, "-B", str(DIRECT_RUNNER), "--test",
        DIRECT_TEST.relative_to(ROOT).as_posix(), "--minimum-tests", "2",
    ], cwd=ROOT)
    if direct["status"] != "PASS":
        failures.append("direct test runner")

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="run-", dir=WORK_ROOT))
    targets: dict[str, bytes] = {}
    target_paths: dict[str, Path] = {}
    target_names: dict[str, str] = {}
    target_rows: dict[str, Any] = {}
    port_rows: dict[str, Any] = {}
    for member_name in module.MEMBER_NAMES:
        config = module.family_configuration(member_name)
        rtl = module.build_verilog({"module": member_name}, {})
        repeat = module.build_verilog({"module": member_name}, {})
        payload = rtl.encode("utf-8")
        declaration = re.search(rf"(?m)^module\s+{re.escape(member_name)}\s*\(", rtl)
        if not rtl or rtl != repeat or declaration is None:
            failures.append(f"export/determinism: {member_name}")
        target_name = f"DelayDut_{len(target_names)}"
        targets[member_name] = rename_module(payload, member_name, target_name)
        target_names[member_name] = target_name
        target_paths[member_name] = work / f"{target_name}.sv"
        target_paths[member_name].write_bytes(targets[member_name])
        actual_ports = {
            (port.name, "input", port.width) for port in config.control_inputs
        } | {
            (field.input_name, "input", field.width) for field in config.data_fields
        } | {
            (port.name, "output", port.width) for port in config.control_outputs
        } | {
            (field.output_name, "output", field.width) for field in config.data_fields
        }
        expected_ports = {
            (port["name"], port["direction"], port_width(port))
            for port in hierarchy[member_name]["ports"]
        }
        port_rows[member_name] = {
            "expected": len(expected_ports),
            "actual": len(actual_ports),
            "matched": expected_ports == actual_ports,
        }
        if expected_ports != actual_ports:
            failures.append(f"port ABI: {member_name}")
        target_rows[member_name] = {
            "mode": config.mode,
            "stages": config.stages,
            "bytes": len(payload),
            "sha256": digest_bytes(payload),
            "deterministic": rtl == repeat,
        }

    locked_modules, locked_sha = extract_locked_modules(
        LOCKED_XSTOP, module.MEMBER_NAMES, hierarchy
    )
    if LOCKED_XSTOP.stat().st_size != LOCKED_BYTES or locked_sha != LOCKED_SHA256:
        failures.append("locked XSTop identity")
    reference_names: dict[str, str] = {}
    reference_rows: dict[str, Any] = {}
    for index, member_name in enumerate(module.MEMBER_NAMES):
        reference_name = f"DelayReference_{index}"
        reference_names[member_name] = reference_name
        renamed = rename_module(locked_modules[member_name], member_name, reference_name)
        reference_rows[member_name] = {
            "bytes": len(locked_modules[member_name]),
            "sha256": digest_bytes(locked_modules[member_name]),
            "line_start": hierarchy[member_name]["start_line"],
            "line_end": hierarchy[member_name]["end_line"],
        }
        locked_modules[member_name] = renamed

    targets_path = work / "DelayFamilyTargets.sv"
    references_path = work / "DelayFamilyReferences.sv"
    miter_path = work / "DelayFamilyMiter.sv"
    targets_path.write_bytes(b"\n".join(targets.values()))
    references_path.write_bytes(b"\n".join(locked_modules.values()))
    max_stages = max(module.family_configuration(name).stages
                     for name in module.MEMBER_NAMES)
    cycles = max_stages + 10
    miter_text, diff_rows = build_miter(
        module, hierarchy, target_names, reference_names, cycles
    )
    miter_path.write_text(miter_text, encoding="utf-8", newline="\n")

    target_linux = wsl_path(targets_path)
    reference_linux = wsl_path(references_path)
    miter_linux = wsl_path(miter_path)
    verilator = run_wsl([
        "verilator", "--lint-only", "--timing", "-Wno-fatal",
        "--top-module", "DelayWaveMiter",
        target_linux, reference_linux, miter_linux,
    ])
    object_dir = wsl_path(work / "obj_dir")
    verilator_build = run_wsl([
        "verilator", "--binary", "--timing", "--assert", "-Wno-fatal",
        "--top-module", "DelayWaveMiter", "--Mdir", object_dir,
        target_linux, reference_linux, miter_linux,
    ])
    verilator_run = {"status": "NOT_RUN"}
    if verilator_build["status"] == "PASS":
        verilator_run = run_wsl([f"{object_dir}/VDelayWaveMiter"])
        if verilator_run["status"] != "PASS" or "DELAY_FAMILY_LOCKED_DIFF_PASS 48" not in verilator_run["output_tail"]:
            failures.append("locked Verilator differential")
    else:
        failures.append("Verilator build")
    if verilator["status"] != "PASS":
        failures.append("Verilator lint")

    yosys_modules: dict[str, Any] = {}
    for member_name, target_name in target_names.items():
        member_linux = wsl_path(target_paths[member_name])
        yosys_modules[member_name] = run_wsl([
            "yosys", "-Q", "-p",
            f"read_verilog -sv {member_linux}; hierarchy -check -top {target_name}; "
            "proc; opt; check; stat",
        ])
        if yosys_modules[member_name]["status"] != "PASS":
            failures.append(f"Yosys check: {member_name}")
    yosys = {
        "status": "PASS" if all(row["status"] == "PASS" for row in yosys_modules.values()) else "FAIL",
        "checked_modules": len(yosys_modules),
        "modules": yosys_modules,
    }

    runner_hash = digest_file(DIRECT_RUNNER)
    mode_counts = {
        mode: sum(1 for name in module.MEMBER_NAMES
                  if module.family_configuration(name).mode == mode)
        for mode in ("plain", "valid", "enabled", "pipe")
    }
    if mode_counts != EXPECTED_COUNTS:
        failures.append("family mode counts")
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_UTILITY_DELAY_WAVE",
        "source_commit": SOURCE_COMMIT,
        "locked_reference": {
            "path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
            "bytes": LOCKED_XSTOP.stat().st_size,
            "sha256": locked_sha,
            "expected_sha256": LOCKED_SHA256,
            "locked_unchanged": locked_sha == LOCKED_SHA256,
        },
        "family": {
            "member_count": len(module.MEMBER_NAMES),
            "mode_counts": mode_counts,
            "members": list(module.MEMBER_NAMES),
            "coverage": "48 reachable zero-child modules; complete public input/output ABI per locked module",
        },
        "direct_runner": {
            "path": DIRECT_RUNNER.relative_to(ROOT).as_posix(),
            "sha256": runner_hash,
            **direct,
        },
        "static": {"py_compile": compile_results, "pyright": pyright},
        "port_surface": port_rows,
        "target_exports": target_rows,
        "locked_modules": reference_rows,
        "differential": {
            "status": "PASS" if verilator_run.get("status") == "PASS" else "FAIL",
            "engine": "Verilator executable, exact locked module slices",
            "cycles_per_module": cycles,
            "startup_uninitialized_cycles": {
                name: diff_rows[name]["startup_uninitialized_cycles"]
                for name in module.MEMBER_NAMES
            },
            "output_policy": "All public outputs compared every cycle after only the resetless startup window; validity/flush never masks initialized payload.",
            "members": diff_rows,
            "verilator_lint": verilator,
            "verilator_build": verilator_build,
            "verilator_run": verilator_run,
        },
        "yosys": yosys,
        "gates": {
            "PY_COMPILE": "PASS" if all(row["status"] == "PASS" for row in compile_results) else "FAIL",
            "PYRIGHT": "PASS" if pyright["status"] == "PASS" else "FAIL",
            "DIRECT_TEST_PASS_BOUNDED": "PASS" if direct["status"] == "PASS" else "FAIL",
            "ABI": "PASS" if all(row["matched"] for row in port_rows.values()) else "FAIL",
            "DETERMINISTIC_EXPORT": "PASS" if all(row["deterministic"] for row in target_rows.values()) else "FAIL",
            "VERILATOR": "PASS" if verilator["status"] == "PASS" and verilator_build["status"] == "PASS" and verilator_run.get("status") == "PASS" else "FAIL",
            "YOSYS": "PASS" if yosys["status"] == "PASS" else "FAIL",
            "FORMAL": "NOT_RUN_COORDINATOR_SERIAL",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "PASS_BOUNDED_REFERENCE_DIFFERENTIAL" if not failures else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "failures": failures,
        "limitations": [
            "DelayReg is the locked one-core specialization with enable tied high; no universal Delayer configuration is claimed.",
            "Resetless state is excluded only during its initial fill window; all public outputs are compared every later cycle.",
            "Formal equivalence is deferred to the coordinator's serialized queue; ACCEPTED remains disallowed.",
        ],
        "work_directory": work.relative_to(ROOT).as_posix(),
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "members": len(module.MEMBER_NAMES),
                      "modes": mode_counts, "failures": failures}))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
