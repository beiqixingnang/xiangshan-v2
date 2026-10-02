"""Run locked-reference executable differentials for completed DCache leaves."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/"
    "Cpu-Memory-Memory.Dcache.MissQueue.Family-Hardware.py"
)
REFERENCE_DIR = ROOT / "validation/reference-sv"
MEMBERS = (
    "MissReadyGen",
    "ProbeEntry",
    "TreeArbiter",
    "WritebackEntry",
    "WritebackEntry_15",
)
IMPLEMENTED_MEMBERS = (
    "MissReadyGen",
    "TreeArbiter",
    "WritebackEntry",
    "WritebackEntry_15",
)
RESETLESS_STARTUP_MEMBERS = {
    "ProbeEntry",
    "WritebackEntry",
    "WritebackEntry_15",
}
RESETLESS_STARTUP_OUTPUTS = {
    "ProbeEntry": (
        "io_pipe_req_bits_probe_param",
        "io_pipe_req_bits_probe_need_data",
        "io_pipe_req_bits_vaddr",
        "io_pipe_req_bits_addr",
        "io_block_addr_bits",
    ),
    "WritebackEntry": (
        "io_mem_release_bits_opcode",
        "io_mem_release_bits_param",
        "io_mem_release_bits_address",
        "io_mem_release_bits_data",
        "io_mem_release_bits_corrupt",
        "io_block_addr_bits",
    ),
    "WritebackEntry_15": (
        "io_mem_release_bits_opcode",
        "io_mem_release_bits_param",
        "io_mem_release_bits_address",
        "io_mem_release_bits_data",
        "io_mem_release_bits_corrupt",
        "io_block_addr_bits",
    ),
}
DIRECT_TEST = ROOT / (
    "python/Program-System/System-Testing/Testing-Cpu/"
    "Testing-Cpu-Memory.Dcache.MissQueue.Family-Hardware.py"
)
DIRECT_TEST_RUNNER = ROOT / "validation/v2_direct_test_runner.py"
SCALA_SOURCES = (
    ROOT / "upstream/src/main/scala/xiangshan/cache/dcache/DCacheWrapper.scala",
    ROOT / "upstream/src/main/scala/xiangshan/cache/dcache/mainpipe/Probe.scala",
    ROOT / "upstream/src/main/scala/xiangshan/cache/dcache/mainpipe/WritebackQueue.scala",
)
EVIDENCE = ROOT / "validation/v2-dcache-completion-wave-results.json"


def load_build() -> Any:
    """Load only the aggregate Build under test."""

    spec = importlib.util.spec_from_file_location("v2_dcache_completion_build", BUILD)
    if spec is None or spec.loader is None:
        raise ImportError(BUILD)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_ansi_ports(source: str, module_name: str) -> tuple[tuple[str, str, int], ...]:
    """Read exact ordered directions and widths from ANSI or legacy port lists."""

    match = re.search(
        rf"\bmodule\s+{re.escape(module_name)}\s*\((.*?)\)\s*;",
        source,
        flags=re.DOTALL,
    )
    if match is None:
        raise ValueError(f"module declaration not found: {module_name}")
    header = re.sub(r"//[^\n]*", "", match.group(1))
    items = [item.strip() for item in header.split(",") if item.strip()]
    ansi_ports: list[tuple[str, str, int]] = []
    current_direction: str | None = None
    current_width = 1
    is_ansi = True
    for item in items:
        declaration = re.fullmatch(
            r"(?:(input|output|inout)\s+)?"
            r"(?:(?:wire|reg|logic)\s+)?"
            r"(?:\[(\d+)\s*:\s*(\d+)\]\s*)?"
            r"([A-Za-z_$][A-Za-z0-9_$]*)",
            item,
            flags=re.DOTALL,
        )
        if declaration is None:
            raise ValueError(f"unparsed {module_name} port declaration: {item!r}")
        explicit_direction, msb, lsb, name = declaration.groups()
        if explicit_direction is not None:
            current_direction = explicit_direction
            current_width = 1 if msb is None else abs(int(msb) - int(lsb)) + 1
        if current_direction is None:
            is_ansi = False
            break
        ansi_ports.append((name, current_direction, current_width))
    if is_ansi:
        return tuple(ansi_ports)

    port_names = [name.strip() for name in items]
    declarations: dict[str, tuple[str, int]] = {}
    body = source[match.end():]
    declaration_pattern = re.compile(
        r"^\s*(input|output|inout)\s+"
        r"(?:(?:wire|reg|logic)\s+)?"
        r"(?:\[(\d+)\s*:\s*(\d+)\]\s*)?([^;]+);",
        flags=re.MULTILINE,
    )
    for direction, msb, lsb, names in declaration_pattern.findall(body):
        width = 1 if msb == "" else abs(int(msb) - int(lsb)) + 1
        for raw_name in names.split(","):
            name = re.sub(r"\b(?:wire|reg|logic)\b", "", raw_name).strip()
            if not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name):
                raise ValueError(f"unparsed {module_name} port declaration: {raw_name!r}")
            declarations[name] = (direction, width)
    missing = [name for name in port_names if name not in declarations]
    if missing:
        raise ValueError(f"missing {module_name} port declarations: {missing}")
    return tuple((name, *declarations[name]) for name in port_names)


def blank_vector(specs: tuple[tuple[str, str, int], ...]) -> dict[str, int]:
    """Return zero values for non-clock inputs in one sample."""

    return {
        name: 0
        for name, direction, _width in specs
        if direction == "input" and name != "clock"
    }


def same_abi(
    left: tuple[tuple[str, str, int], ...],
    right: tuple[tuple[str, str, int], ...],
) -> bool:
    """Compare every port name, direction, and width independent of print order."""

    return len(left) == len(right) and sorted(left) == sorted(right)


def directed_vectors(
    member: str, specs: tuple[tuple[str, str, int], ...]
) -> list[dict[str, int]]:
    """Create request, priority, backpressure, response, and beat sequences."""

    vectors: list[dict[str, int]] = []
    if member == "MissReadyGen":
        for valid_mask in range(8):
            for ready_mask in range(16):
                vector = blank_vector(specs)
                for index in range(3):
                    vector[f"io_in_{index}_valid"] = (valid_mask >> index) & 1
                for index in range(4):
                    vector[f"io_queryMQ_{index}_ready"] = (ready_mask >> index) & 1
                    vector[f"io_in_{index}_bits_source"] = (valid_mask + 3 * index) & 0xF
                    vector[f"io_in_{index}_bits_addr"] = (
                        0x1200 + 0x101 * index + valid_mask
                    ) & ((1 << 48) - 1)
                    vector[f"io_in_{index}_bits_vaddr"] = (
                        0x5000 + 0x203 * index + valid_mask
                    ) & ((1 << 50) - 1)
                vectors.append(vector)
    elif member == "TreeArbiter":
        for valid_mask in range(16):
            vector = blank_vector(specs)
            for index in range(4):
                vector[f"io_in_{index}_valid"] = (valid_mask >> index) & 1
                prefix = f"io_in_{index}_bits_"
                for name, direction, width in specs:
                    if direction == "input" and name.startswith(prefix):
                        field = name[len(prefix):]
                        vector[name] = (
                            (valid_mask + 1) * 0x13579BDF
                            ^ (index + 5) * 0x2468ACE1
                            ^ sum(field.encode("ascii"))
                        ) & ((1 << width) - 1)
            vectors.append(vector)
    elif member == "ProbeEntry":
        vectors.extend(
            [
                {
                    **blank_vector(specs),
                    "io_id": 5,
                    "io_req_valid": 1,
                    "io_req_bits_addr": 0x1234,
                    "io_req_bits_vaddr": 0x2A1234,
                    "io_req_bits_param": 2,
                    "io_req_bits_needData": 1,
                    "io_lrsc_locked_block_valid": 1,
                    "io_lrsc_locked_block_bits": 0x1237,
                    "io_pipe_req_ready": 1,
                },
                {
                    **blank_vector(specs),
                    "io_id": 5,
                    "io_lrsc_locked_block_valid": 1,
                    "io_lrsc_locked_block_bits": 0x1237,
                    "io_pipe_req_ready": 1,
                },
                {
                    **blank_vector(specs),
                    "io_id": 5,
                    "io_lrsc_locked_block_valid": 0,
                    "io_pipe_req_ready": 1,
                },
                {
                    **blank_vector(specs),
                    "io_id": 5,
                    "io_pipe_req_ready": 0,
                },
                {
                    **blank_vector(specs),
                    "io_id": 5,
                    "io_pipe_req_ready": 1,
                },
                {
                    **blank_vector(specs),
                    "io_id": 5,
                    "io_pipe_resp_valid": 1,
                    "io_pipe_resp_bits_id": 4,
                },
                {
                    **blank_vector(specs),
                    "io_id": 5,
                    "io_pipe_resp_valid": 1,
                    "io_pipe_resp_bits_id": 5,
                },
            ]
        )
    elif member in ("WritebackEntry", "WritebackEntry_15"):
        source_id = 43 if member == "WritebackEntry_15" else 17
        data = int("0123456789abcdef" * 4, 16) | (
            int("fedcba9876543210" * 4, 16) << 256
        )
        vectors.extend(
            [
                {
                    **blank_vector(specs),
                    "io_id": source_id,
                    "io_req_valid": 1,
                    "io_primary_valid": 1,
                    "io_req_bits_param": 5,
                    "io_req_bits_voluntary": 0,
                    "io_req_bits_hasData": 1,
                    "io_req_bits_corrupt": 1,
                    "io_req_bits_dirty": 1,
                    "io_req_bits_addr": 0x123456789ABC,
                    "io_req_data_data": data,
                },
                {
                    **blank_vector(specs),
                    "io_id": source_id,
                    "io_req_data_data": data,
                },
                {
                    **blank_vector(specs),
                    "io_id": source_id,
                    "io_req_data_data": data,
                    "io_mem_release_ready": 1,
                },
                {
                    **blank_vector(specs),
                    "io_id": source_id,
                    "io_req_data_data": data,
                    "io_mem_release_ready": 1,
                },
                {
                    **blank_vector(specs),
                    "io_id": source_id,
                    "io_req_valid": 1,
                    "io_primary_valid": 1,
                    "io_req_bits_param": 3,
                    "io_req_bits_voluntary": 1,
                    "io_req_bits_hasData": 0,
                    "io_req_bits_corrupt": 0,
                    "io_req_bits_dirty": 0,
                    "io_req_bits_addr": 0x4000,
                },
                {
                    **blank_vector(specs),
                    "io_id": source_id,
                    "io_mem_release_ready": 1,
                },
                {
                    **blank_vector(specs),
                    "io_id": source_id,
                    "io_mem_grant_valid": 0,
                },
                {
                    **blank_vector(specs),
                    "io_id": source_id,
                    "io_mem_grant_valid": 1,
                },
            ]
        )
    return vectors


def add_random_vectors(
    member: str,
    specs: tuple[tuple[str, str, int], ...],
    vectors: list[dict[str, int]],
) -> None:
    """Extend directed cases with deterministic input and reset activity."""

    rng = random.Random(0xDCA5E + sum(member.encode("ascii")))
    for cycle in range(64):
        vector = blank_vector(specs)
        for name, direction, width in specs:
            if direction != "input" or name == "clock":
                continue
            if name == "reset":
                vector[name] = int(cycle in (19, 47))
            else:
                vector[name] = rng.getrandbits(width)
        if member in ("WritebackEntry", "WritebackEntry_15"):
            vector["io_req_bits_dirty"] = vector["io_req_bits_hasData"]
        vectors.append(vector)


def make_testbench(
    member: str,
    specs: tuple[tuple[str, str, int], ...],
    vectors: list[dict[str, int]],
) -> str:
    """Build an identical input trace printer for one source at a time."""

    inputs = [
        (name, width)
        for name, direction, width in specs
        if direction == "input"
    ]
    outputs = [
        (name, width)
        for name, direction, width in specs
        if direction == "output"
    ]
    stateful = any(name == "clock" for name, _width in inputs)
    declarations: list[str] = []
    connections: list[str] = []
    initial_values: list[str] = []
    for name, width in inputs:
        if width == 1:
            declarations.append(f"  reg {name};")
        else:
            declarations.append(f"  reg [{width - 1}:0] {name};")
        connections.append(f"    .{name}({name})")
        if name != "clock":
            initial_values.append(f"    {name} = {width}'h0;")
    output_names: list[str] = []
    for index, (name, width) in enumerate(outputs):
        output_name = f"observed_{index}"
        output_names.append(output_name)
        if width == 1:
            declarations.append(f"  wire {output_name};")
        else:
            declarations.append(f"  wire [{width - 1}:0] {output_name};")
        connections.append(f"    .{name}({output_name})")
    joined_connections = ",\n".join(connections)
    output_formats = " ".join("%h" for _ in outputs)
    output_values = ", ".join(output_names)
    lines = [
        "module tb;",
        *declarations,
        f"  {member} target (",
        joined_connections,
        "  );",
        "  task dump;",
        "    input integer cycle;",
        "    input integer phase;",
        "    begin",
        f'      $display("V:%0d:%0d {output_formats}", cycle, phase, {output_values});',
        "    end",
        "  endtask",
        "  integer cycle;",
        "  initial begin",
        *initial_values,
    ]
    if stateful:
        lines.extend(
            [
                "    clock = 1'b0;",
                "    reset = 1'b1;",
                "    #1;",
                "    clock = 1'b1;",
                "    #1;",
                "    dump(-1, 1);",
                "    clock = 1'b0;",
                "    #1;",
                "    reset = 1'b0;",
                "    #1;",
                "    dump(-1, 0);",
            ]
        )
    else:
        lines.extend(["    #1;", "    dump(-1, 0);"])
    for cycle, vector in enumerate(vectors):
        for name, _width in inputs:
            if name == "clock" or name not in vector:
                continue
            width = next(port_width for port_name, port_width in inputs if port_name == name)
            lines.append(f"    {name} = {width}'h{vector[name]:x};")
        lines.append("    #1;")
        lines.append(f"    dump({cycle}, 0);")
        if stateful:
            lines.extend(
                [
                    "    clock = 1'b1;",
                    "    #1;",
                    f"    dump({cycle}, 1);",
                    "    clock = 1'b0;",
                    "    #1;",
                ]
            )
    lines.extend(["    $display(\"PASS\");", "    $finish;", "  end", "endmodule", ""])
    return "\n".join(lines)


def wsl_path(path: Path) -> str:
    """Translate a mounted Windows drive path for the Debian WSL toolchain."""

    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if len(drive) != 1 or not resolved.is_absolute():
        raise ValueError(f"expected an absolute mounted drive path: {resolved}")
    return "/mnt/" + drive + "/" + "/".join(resolved.parts[1:])


def create_wsl_temp_dir() -> str:
    """Create one isolated native-filesystem build directory for Verilator."""

    result = subprocess.run(
        ["wsl.exe", "-d", "Debian", "--", "mktemp", "-d", "/tmp/v2-dcache-completion-wave.XXXXXX"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    path = result.stdout.strip()
    if not path.startswith("/tmp/v2-dcache-completion-wave."):
        raise RuntimeError(f"unexpected WSL temporary directory: {path!r}")
    return path


def remove_wsl_temp_dir(path: str) -> None:
    """Remove only the WSL temporary directory created by this validator."""

    if not path.startswith("/tmp/v2-dcache-completion-wave."):
        raise ValueError(f"refusing to remove an unowned temporary path: {path}")
    subprocess.run(
        ["wsl.exe", "-d", "Debian", "--", "rm", "-rf", "--", path],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def run_verilator(
    source: Path, bench: Path, object_dir: str, binary: str
) -> dict[str, Any]:
    """Compile and execute one locked source or Amaranth-export source."""

    compile_command = [
        "wsl.exe", "-d", "Debian", "--", "verilator", "--binary", "--timing",
        "-Wno-fatal", "-DSYNTHESIS", "--top-module", "tb", "--Mdir",
        object_dir, "-o", binary, wsl_path(source), wsl_path(bench),
    ]
    compile_result = subprocess.run(
        compile_command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if compile_result.returncode != 0:
        raise RuntimeError(
            f"Verilator compile failed for {source.name}:\n"
            f"{compile_result.stdout}{compile_result.stderr}"
        )
    simulation_command = ["wsl.exe", "-d", "Debian", "--", binary]
    run_result = subprocess.run(
        simulation_command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if run_result.returncode != 0:
        raise RuntimeError(
            f"Verilator run failed for {source.name}:\n"
            f"{run_result.stdout}{run_result.stderr}"
        )
    samples = tuple(
        line.strip()
        for line in run_result.stdout.splitlines()
        if line.startswith("V:")
    )
    if not samples:
        raise RuntimeError(f"Verilator produced no output samples for {source.name}")
    sample_payload = "\n".join(samples).encode("utf-8")
    return {
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "sample_sha256": hashlib.sha256(sample_payload).hexdigest(),
        "samples": samples,
        "compile": {
            "command": compile_command,
            "status": "PASS" if compile_result.returncode == 0 else "FAIL",
            "returncode": compile_result.returncode,
            "output_tail": (compile_result.stdout + compile_result.stderr)[-1200:],
        },
        "simulation": {
            "command": simulation_command,
            "status": "PASS" if run_result.returncode == 0 else "FAIL",
            "returncode": run_result.returncode,
            "output_tail": run_result.stdout[-1200:],
            "stderr_tail": run_result.stderr[-1200:],
        },
    }


def source_record(path: Path) -> dict[str, Any]:
    """Bind one input to this non-counting differential receipt."""

    resolved = path.resolve()
    return {
        "path": resolved.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        "bytes": resolved.stat().st_size,
    }


def run_preparation_checks() -> dict[str, Any]:
    """Run syntax, direct tests, Pyright, and record the simulation tool version."""

    compile_command = [
        sys.executable,
        "-B",
        "-m",
        "py_compile",
        str(BUILD),
        str(DIRECT_TEST),
        str(Path(__file__).resolve()),
    ]
    compile_result = subprocess.run(
        compile_command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    direct_command = [
        sys.executable,
        "-B",
        str(DIRECT_TEST_RUNNER),
        "--test",
        DIRECT_TEST.relative_to(ROOT).as_posix(),
        "--minimum-tests",
        "9",
    ]
    direct_result = subprocess.run(
        direct_command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    direct_output = direct_result.stdout + direct_result.stderr
    test_count_match = re.search(r"Ran\s+(\d+)\s+tests?", direct_output)
    test_count = 0 if test_count_match is None else int(test_count_match.group(1))
    pyright_command = [
        "pyright.cmd",
        str(BUILD),
        str(DIRECT_TEST),
        str(Path(__file__).resolve()),
    ]
    pyright_result = subprocess.run(
        pyright_command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    verilator_command = ["wsl.exe", "-d", "Debian", "--", "verilator", "--version"]
    verilator_result = subprocess.run(
        verilator_command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if compile_result.returncode != 0:
        raise RuntimeError("py_compile failed:\n" + compile_result.stderr)
    if direct_result.returncode != 0 or test_count < 9:
        raise RuntimeError(
            f"direct test failed or discovered only {test_count} tests:\n{direct_output[-3000:]}"
        )
    if pyright_result.returncode != 0:
        raise RuntimeError("targeted Pyright failed:\n" + pyright_result.stdout + pyright_result.stderr)
    if verilator_result.returncode != 0:
        raise RuntimeError("Verilator version probe failed:\n" + verilator_result.stderr)
    return {
        "py_compile": {
            "command": compile_command,
            "status": "PASS",
            "returncode": compile_result.returncode,
        },
        "direct_test": {
            "command": direct_command,
            "status": "PASS",
            "returncode": direct_result.returncode,
            "tests_run": test_count,
            "output_tail": direct_output[-1800:],
        },
        "pyright": {
            "command": pyright_command,
            "status": "PASS",
            "returncode": pyright_result.returncode,
            "output_tail": (pyright_result.stdout + pyright_result.stderr)[-1800:],
        },
        "verilator": {
            "command": verilator_command,
            "status": "PASS",
            "returncode": verilator_result.returncode,
            "version": verilator_result.stdout.strip(),
        },
    }


def verify_member(
    build: Any, member: str, work_dir: Path, wsl_work_dir: str
) -> dict[str, Any]:
    """Check exact ABI and compare every public output over a deterministic trace."""

    specs = tuple(build.PORT_SPECS[member])
    reference_path = REFERENCE_DIR / f"{member}.sv"
    reference_source = reference_path.read_text(encoding="utf-8")
    reference_specs = parse_ansi_ports(reference_source, member)
    if not same_abi(specs, reference_specs):
        raise AssertionError(f"{member}: Build ABI differs from locked reference ABI")
    exported = build.build_verilog({"module": member}, {})
    exported_again = build.build_verilog({"module": member}, {})
    if exported != exported_again:
        raise AssertionError(f"{member}: export is not deterministic")
    if not same_abi(parse_ansi_ports(exported, member), reference_specs):
        raise AssertionError(f"{member}: generated Verilog ABI differs from locked reference")

    vectors = directed_vectors(member, specs)
    add_random_vectors(member, specs, vectors)
    bench = work_dir / f"{member}_tb.sv"
    bench.write_text(make_testbench(member, specs, vectors), encoding="utf-8", newline="\n")
    exported_path = work_dir / f"{member}_amaranth.sv"
    exported_path.write_text(exported, encoding="utf-8", newline="\n")
    reference_run = run_verilator(
        reference_path,
        bench,
        f"{wsl_work_dir}/{member}_reference_obj",
        f"{wsl_work_dir}/{member}_reference",
    )
    exported_run = run_verilator(
        exported_path,
        bench,
        f"{wsl_work_dir}/{member}_amaranth_obj",
        f"{wsl_work_dir}/{member}_amaranth",
    )
    reference_samples = reference_run["samples"]
    exported_samples = exported_run["samples"]
    if reference_samples != exported_samples:
        for index, (reference, candidate) in enumerate(
            zip(reference_samples, exported_samples)
        ):
            if reference != candidate:
                raise AssertionError(
                    f"{member}: output mismatch at sample {index}\n"
                    f"locked: {reference}\nAmaranth: {candidate}"
                )
        raise AssertionError(
            f"{member}: sample count differs: locked={len(reference_samples)} "
            f"Amaranth={len(exported_samples)}"
        )
    unknown_samples = sum(
        any(character in token.lower() for character in "xz")
        for line in reference_samples
        for token in line.split()[1:]
    )
    if member == "ProbeEntry":
        status = "PASS_BOUNDED_CLOSURE_PENDING"
    elif member in RESETLESS_STARTUP_MEMBERS:
        status = "PASS_BOUNDED_RESETLESS_STARTUP_UNCLAIMED"
    elif unknown_samples:
        status = "PASS_BOUNDED_UNKNOWN_STARTUP"
    else:
        status = "PASS"
    output_names = [
        name for name, direction, _width in specs if direction == "output"
    ]
    port_signature = [
        {"name": name, "direction": direction, "width": width}
        for name, direction, width in sorted(specs)
    ]
    result = {
        "status": status,
        "abi": {
            "status": "PASS",
            "port_count": len(specs),
            "input_count": sum(direction == "input" for _name, direction, _width in specs),
            "output_count": len(output_names),
            "ports": port_signature,
            "build_matches_locked_reference": True,
            "amaranth_export_matches_locked_reference": True,
            "deterministic_export": True,
        },
        "executable_differential": {
            "status": "PASS_BOUNDED",
            "sample_count": len(reference_samples),
            "unknown_output_samples": unknown_samples,
            "all_public_outputs_compared": True,
            "outputs_compared": output_names,
            "payloads_compared_when_valid_is_low": True,
            "resetless_startup_unclaimed": member in RESETLESS_STARTUP_MEMBERS,
            "resetless_startup_outputs": list(RESETLESS_STARTUP_OUTPUTS.get(member, ())),
            "trace_sha256": hashlib.sha256(
                "\n".join(
                    key + "=" + str(value)
                    for vector in vectors
                    for key, value in sorted(vector.items())
                ).encode("utf-8")
            ).hexdigest(),
            "reference": {
                "source": source_record(reference_path),
                "rtl_sha256": reference_run["source_sha256"],
                "sample_sha256": reference_run["sample_sha256"],
                "compile": reference_run["compile"],
                "simulation": reference_run["simulation"],
            },
            "amaranth_export": {
                "rtl_sha256": exported_run["source_sha256"],
                "sample_sha256": exported_run["sample_sha256"],
                "compile": exported_run["compile"],
                "simulation": exported_run["simulation"],
            },
        },
    }
    print(
        f"{member}: ABI={len(specs)} ports, outputs="
        f"{sum(direction == 'output' for _name, direction, _width in specs)}, "
        f"samples={len(reference_samples)}, unknown_output_samples={unknown_samples}, "
        f"resetless_startup_unclaimed={member in RESETLESS_STARTUP_MEMBERS}, "
        f"reference_sha256={reference_run['source_sha256']}, status={status}"
    )
    return result


def main() -> int:
    """Validate completed and pending leaves, then write a non-counting receipt."""

    build = load_build()
    if not set(IMPLEMENTED_MEMBERS).issubset(build.IMPLEMENTED_MEMBERS):
        raise AssertionError("a differentially checked member is not declared implemented")
    if "ProbeEntry" not in build.CONTRACT_ONLY_MEMBERS:
        raise AssertionError("ProbeEntry must remain visible as pending full closure")
    preparation = run_preparation_checks()
    member_results: dict[str, Any] = {}
    wsl_work_dir = create_wsl_temp_dir()
    try:
        with tempfile.TemporaryDirectory(prefix="v2_dcache_completion_wave_") as directory:
            work_dir = Path(directory)
            for member in MEMBERS:
                member_results[member] = verify_member(
                    build, member, work_dir, wsl_work_dir
                )
    finally:
        remove_wsl_temp_dir(wsl_work_dir)
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_DCACHE_COMPLETION_WAVE",
        "build_id": "Build-Cpu.Memory.Dcache.MissQueue.Family",
        "direct_test_id": "Build-Cpu.Memory.Dcache.MissQueue.Family",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "status": "PASS_BOUNDED",
        "strict_complete_build_count_delta": 0,
        "acceptance_eligible": False,
        "formal_run": False,
        "sources": {
            "python_build": source_record(BUILD),
            "direct_test": source_record(DIRECT_TEST),
            "direct_test_runner": source_record(DIRECT_TEST_RUNNER),
            "validator": source_record(Path(__file__).resolve()),
            "scala": [source_record(path) for path in SCALA_SOURCES],
            "locked_references": [
                source_record(REFERENCE_DIR / f"{member}.sv") for member in MEMBERS
            ],
        },
        "checks": preparation,
        "implementation_declarations": {
            "implemented_members": list(build.IMPLEMENTED_MEMBERS),
            "contract_only_members": list(build.CONTRACT_ONLY_MEMBERS),
        },
        "members": member_results,
        "unclosed": [
            "CMOUnit and MissEntry remain CONTRACT_ONLY pending complete state, data, and TileLink behavior.",
            "ProbeEntry remains CONTRACT_ONLY; its differential is bounded and its reset-less startup state is unclaimed.",
            "WritebackEntry and WritebackEntry_15 reset-less startup state is unclaimed by bounded simulation.",
            "Formal equivalence, reset-entry proof, full MissQueue aggregate, and parent DCache closure remain pending.",
            "The prior WritebackEntry 843/843 receipt was bound to the pre-wave Build hash; the coordinator must decide whether the current source-key requires a serial focused rerun.",
        ],
    }
    EVIDENCE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Receipt: {EVIDENCE.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
