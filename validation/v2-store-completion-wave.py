"""Run full-output bounded differentials for the locked V2 store family."""

from __future__ import annotations

import argparse
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
    "Cpu-Memory-Memory.Store.Family-Hardware.py"
)
DIRECT = ROOT / (
    "python/Program-System/System-Testing/Testing-Cpu/"
    "Testing-Cpu-Memory.Store.Family-Hardware.py"
)
DIRECT_RUNNER = ROOT / "validation/v2_direct_test_runner.py"
REFERENCE_DIR = ROOT / "validation/reference-sv"
EVIDENCE = ROOT / "validation/v2-store-completion-wave-results.json"
SCALA_SOURCES = (
    ROOT / "upstream/src/main/scala/xiangshan/mem/sbuffer/Sbuffer.scala",
    ROOT / "upstream/src/main/scala/xiangshan/mem/lsqueue/StoreQueue.scala",
    ROOT / "upstream/src/main/scala/xiangshan/mem/lsqueue/StoreMisalignBuffer.scala",
    ROOT / "upstream/src/main/scala/xiangshan/mem/pipeline/StoreUnit.scala",
)
MEMBERS = (
    "SbufferData",
    "StoreExceptionBuffer",
    "StoreMisalignBuffer",
    "StoreUnit",
)
RESETLESS_STARTUP_OUTPUTS = {
    "SbufferData": tuple(
        f"io_dataOut_{line}_{word}_{byte}"
        for line in range(16)
        for word in range(4)
        for byte in range(16)
    ),
    "StoreExceptionBuffer": (
        "io_exceptionAddr_vaddr",
        "io_exceptionAddr_vaNeedExt",
        "io_exceptionAddr_isHyper",
        "io_exceptionAddr_gpaddr",
        "io_exceptionAddr_isForVSnonLeafPTE",
    ),
    "StoreMisalignBuffer": (
        "io_splitStoreReq_bits_vaddr",
        "io_splitStoreReq_bits_mask",
        "io_writeBack_bits_uop_robIdx_value",
        "io_vecWriteBack_0_bits_vaddr",
        "io_sqControl_toStoreQueue_paddr",
    ),
    "StoreUnit": (
        "io_lsq_replenish_bits_paddr",
        "io_lsq_replenish_bits_gpaddr",
        "io_debug_ls_addr",
    ),
}


def load_build() -> Any:
    """Load the exact aggregate Build from its isolated path."""

    spec = importlib.util.spec_from_file_location("v2_store_completion_build", BUILD)
    if spec is None or spec.loader is None:
        raise ImportError(BUILD)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_ports(source: str, module_name: str) -> tuple[tuple[str, str, int], ...]:
    """Parse exact ANSI reference or legacy Amaranth Verilog port declarations."""

    match = re.search(
        rf"\bmodule\s+{re.escape(module_name)}\s*\((.*?)\)\s*;",
        source,
        flags=re.DOTALL,
    )
    if match is None:
        raise ValueError(f"module declaration missing: {module_name}")
    header = re.sub(r"//[^\n]*", "", match.group(1))
    items = [item.strip() for item in header.split(",") if item.strip()]
    ports: list[tuple[str, str, int]] = []
    direction: str | None = None
    current_width = 1
    ansi = True
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
            raise ValueError(f"unparsed {module_name} header item {item!r}")
        explicit, msb, lsb, name = declaration.groups()
        if explicit is not None:
            direction = explicit
            current_width = 1 if msb is None else abs(int(msb) - int(lsb)) + 1
        if direction is None:
            ansi = False
            break
        ports.append((name, direction, current_width))
    if ansi:
        return tuple(ports)

    names = [item.strip() for item in items]
    declarations: dict[str, tuple[str, int]] = {}
    body = source[match.end():]
    pattern = re.compile(
        r"^\s*(input|output|inout)\s+"
        r"(?:(?:wire|reg|logic)\s+)?"
        r"(?:\[(\d+)\s*:\s*(\d+)\]\s*)?([^;]+);",
        flags=re.MULTILINE,
    )
    for port_direction, msb, lsb, group in pattern.findall(body):
        width = 1 if msb == "" else abs(int(msb) - int(lsb)) + 1
        for raw_name in group.split(","):
            port_name = re.sub(r"\b(?:wire|reg|logic)\b", "", raw_name).strip()
            if not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", port_name):
                raise ValueError(f"unparsed {module_name} declaration {raw_name!r}")
            declarations[port_name] = (port_direction, width)
    missing = [name for name in names if name not in declarations]
    if missing:
        raise ValueError(f"{module_name} missing body declarations: {missing[:8]}")
    return tuple((name, *declarations[name]) for name in names)


def same_abi(
    left: tuple[tuple[str, str, int], ...],
    right: tuple[tuple[str, str, int], ...],
) -> bool:
    """Compare every port name, direction, and width independent of print order."""

    return len(left) == len(right) and sorted(left) == sorted(right)


def blank_vector(specs: tuple[tuple[str, str, int], ...]) -> dict[str, int]:
    """Create a complete zero-input vector except for the driven clock."""

    return {
        name: 0
        for name, direction, _width in specs
        if direction == "input" and name != "clock"
    }


def _exception_candidate(
    specs: tuple[tuple[str, str, int], ...],
    index: int,
    *,
    rob: int,
    uop: int,
    vaddr: int,
    gpaddr: int,
    exc: int = 7,
    va_need_ext: int = 0,
    hyper: int = 0,
) -> dict[str, int]:
    """Return one locked exception enqueue vector using available flattened fields."""

    port_names = {name for name, _direction, _width in specs}
    prefix = f"io_storeAddrIn_{index}"
    values = {
        f"{prefix}_valid": 1,
        f"{prefix}_bits_uop_uopIdx": uop,
        f"{prefix}_bits_uop_robIdx_flag": (rob >> 8) & 1,
        f"{prefix}_bits_uop_robIdx_value": rob & 0xFF,
        f"{prefix}_bits_fullva": vaddr,
    }
    for exception_bit in (3, 6, 7, 15, 19, 23):
        name = f"{prefix}_bits_uop_exceptionVec_{exception_bit}"
        if name in port_names:
            values[name] = int(exception_bit == exc)
    for suffix, value in (
        ("vaNeedExt", va_need_ext),
        ("gpaddr", gpaddr),
        ("isHyper", hyper),
        ("isForVSnonLeafPTE", 0),
    ):
        name = f"{prefix}_bits_{suffix}"
        if name in port_names:
            values[name] = value
    return values


def _write_req(
    port: int,
    *,
    line: int,
    mask: int,
    data: int,
    offset: int,
    wline: int = 0,
) -> dict[str, int]:
    """Create one SbufferData request vector."""

    prefix = f"io_writeReq_{port}"
    return {
        f"{prefix}_valid": 1,
        f"{prefix}_bits_wvec": 1 << line,
        f"{prefix}_bits_mask": mask,
        f"{prefix}_bits_data": data,
        f"{prefix}_bits_vwordOffset": offset,
        f"{prefix}_bits_wline": wline,
    }


def directed_vectors(
    member: str, specs: tuple[tuple[str, str, int], ...]
) -> list[dict[str, int]]:
    """Create delayed, collision, flush, ROB-order, and handshake cases."""

    vectors: list[dict[str, int]] = []
    if member == "SbufferData":
        vectors.extend(
            [
                {
                    **blank_vector(specs),
                    **_write_req(
                        0, line=3, mask=1 << 1,
                        data=int("0123456789abcdef", 16), offset=2,
                    ),
                },
                blank_vector(specs),
                {
                    **blank_vector(specs),
                    "io_maskFlushReq_0_valid": 1,
                    "io_maskFlushReq_0_bits_wvec": 1 << 3,
                },
                blank_vector(specs),
                {
                    **blank_vector(specs),
                    **_write_req(0, line=5, mask=1, data=0x11, offset=0),
                    **_write_req(1, line=5, mask=1, data=0xAA, offset=0),
                },
                blank_vector(specs),
                {
                    **blank_vector(specs),
                    **_write_req(
                        0, line=7, mask=0,
                        data=int("0123456789abcdef" * 2, 16), offset=1, wline=1,
                    ),
                },
                blank_vector(specs),
                {**blank_vector(specs), "reset": 1},
                blank_vector(specs),
            ]
        )
    elif member == "StoreExceptionBuffer":
        vectors.extend(
            [
                {
                    **blank_vector(specs),
                    **_exception_candidate(specs, 0, rob=7, uop=6, vaddr=0x7000, gpaddr=0x17000, exc=15),
                    **_exception_candidate(specs, 1, rob=3, uop=1, vaddr=0x3000, gpaddr=0x13000, exc=7, va_need_ext=1, hyper=1),
                },
                blank_vector(specs),
                {
                    **blank_vector(specs),
                    **_exception_candidate(specs, 2, rob=4, uop=0, vaddr=0x4000, gpaddr=0x14000, exc=23),
                },
                blank_vector(specs),
                {
                    **blank_vector(specs),
                    "io_redirect_valid": 1,
                    "io_redirect_bits_level": 1,
                    "io_redirect_bits_robIdx_flag": 0,
                    "io_redirect_bits_robIdx_value": 3,
                },
                {
                    **blank_vector(specs),
                    **_exception_candidate(specs, 3, rob=5, uop=0, vaddr=0x5000, gpaddr=0x15000, exc=19),
                },
                blank_vector(specs),
            ]
        )
    elif member == "StoreMisalignBuffer":
        vectors.extend(
            [
                {
                    **blank_vector(specs),
                    "io_enq_0_req_valid": 1,
                    "io_enq_0_req_bits_uop_fuOpType": 0,
                    "io_enq_0_req_bits_uop_uopIdx": 3,
                    "io_enq_0_req_bits_uop_robIdx_flag": 0,
                    "io_enq_0_req_bits_uop_robIdx_value": 4,
                    "io_enq_0_req_bits_vaddr": 0x1000,
                    "io_enq_0_req_bits_mask": 1,
                    "io_splitStoreReq_ready": 0,
                },
                blank_vector(specs),
                {**blank_vector(specs), "io_splitStoreReq_ready": 1},
                {**blank_vector(specs), "io_splitStoreResp_valid": 1, "io_splitStoreResp_bits_vaddr": 0x1000},
                blank_vector(specs),
                {**blank_vector(specs), "io_writeBack_ready": 0},
                {**blank_vector(specs), "io_writeBack_ready": 1},
            ]
        )
    elif member == "StoreUnit":
        vectors.extend(
            [
                {
                    **blank_vector(specs),
                    "io_stin_valid": 1,
                    "io_stin_bits_src_0": 0x12345678,
                    "io_stin_bits_uop_robIdx_flag": 0,
                    "io_stin_bits_uop_robIdx_value": 7,
                    "io_stin_bits_uop_uopIdx": 2,
                    "io_stin_bits_uop_fuOpType": 0,
                },
                blank_vector(specs),
                {
                    **blank_vector(specs),
                    "io_tlb_resp_valid": 1,
                    "io_tlb_resp_bits_miss": 0,
                    "io_tlb_resp_bits_paddr_0": 0x23456000,
                },
                blank_vector(specs),
                {
                    **blank_vector(specs),
                    "io_prefetch_req_valid": 1,
                    "io_prefetch_req_bits_vaddr": 0x4000,
                    "io_dcache_req_ready": 1,
                },
                blank_vector(specs),
            ]
        )
    return vectors


def add_random_vectors(
    member: str,
    specs: tuple[tuple[str, str, int], ...],
    vectors: list[dict[str, int]],
) -> None:
    """Add deterministic input activity, including reset pulses."""

    rng = random.Random(0x5702E + sum(member.encode("ascii")))
    for cycle in range(32):
        vector = blank_vector(specs)
        for name, direction, width in specs:
            if direction != "input" or name == "clock":
                continue
            if name == "reset":
                vector[name] = int(cycle in (13, 25))
            else:
                vector[name] = rng.getrandbits(width)
        vectors.append(vector)


def output_slice_layout(
    specs: tuple[tuple[str, str, int], ...], chunk_limit: int = 4096
) -> tuple[list[dict[str, Any]], list[list[tuple[str, int]]]]:
    """Pack every output in ABI order while respecting Verilator print limits."""

    slices: list[dict[str, Any]] = []
    chunks: list[list[tuple[str, int]]] = []
    current_chunk: list[tuple[str, int]] = []
    current_width = 0
    global_offset = 0
    chunk_offset = 0
    for name, direction, width in specs:
        if direction != "output":
            continue
        if current_chunk and current_width + width > chunk_limit:
            chunks.append(current_chunk)
            current_chunk = []
            current_width = 0
        slices.append(
            {
                "name": name,
                "lsb": global_offset,
                "msb": global_offset + width - 1,
                "width": width,
                "display_chunk": len(chunks),
                "chunk_lsb": current_width,
                "chunk_msb": current_width + width - 1,
            }
        )
        current_chunk.append((name, width))
        current_width += width
        global_offset += width
    if current_chunk:
        chunks.append(current_chunk)
    return slices, chunks


def make_testbench(
    member: str,
    specs: tuple[tuple[str, str, int], ...],
    vectors: list[dict[str, int]],
) -> str:
    """Print every public output at each pre/post-clock sample."""

    inputs = [(name, width) for name, direction, width in specs if direction == "input"]
    outputs = [(name, width) for name, direction, width in specs if direction == "output"]
    stateful = any(name == "clock" for name, _width in inputs)
    declarations: list[str] = []
    connections: list[str] = []
    initial_values: list[str] = []
    for name, width in inputs:
        decl = f"reg [{width - 1}:0] {name};" if width > 1 else f"reg {name};"
        declarations.append("  " + decl)
        connections.append(f"    .{name}({name})")
        if name != "clock":
            initial_values.append(f"    {name} = {width}'h0;")
    output_signals: list[tuple[str, str, int]] = []
    for index, (name, width) in enumerate(outputs):
        out_name = f"observed_{index}"
        output_signals.append((name, out_name, width))
        decl = f"wire [{width - 1}:0] {out_name};" if width > 1 else f"wire {out_name};"
        declarations.append("  " + decl)
        connections.append(f"    .{name}({out_name})")
    _slices, output_chunks = output_slice_layout(specs)
    for chunk_index, chunk in enumerate(output_chunks):
        chunk_width = sum(width for _name, width in chunk)
        declarations.append(
            f"  wire [{chunk_width - 1}:0] observed_chunk_{chunk_index};"
        )
        chunk_names = [
            signal
            for name, signal, _width in output_signals
            if any(name == chunk_name for chunk_name, _chunk_width in chunk)
        ]
        declarations.append(
            f"  assign observed_chunk_{chunk_index} = "
            f"{{{', '.join(reversed(chunk_names))}}};"
        )
    lines = [
        "module tb;",
        *declarations,
        f"  {member} target (",
        ",\n".join(connections),
        "  );",
        "  task dump;",
        "    input integer cycle;",
        "    input integer phase;",
        "    begin",
        *[
            f'      $display("V:%0d:%0d:{chunk_index} %h", cycle, phase, observed_chunk_{chunk_index});'
            for chunk_index in range(len(output_chunks))
        ],
        "    end",
        "  endtask",
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
    input_widths = dict(inputs)
    for cycle, vector in enumerate(vectors):
        for name, width in inputs:
            if name == "clock" or name not in vector:
                continue
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
    """Translate one absolute mounted Windows drive path for WSL."""

    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if len(drive) != 1 or not resolved.is_absolute():
        raise ValueError(f"expected an absolute mounted path: {resolved}")
    return "/mnt/" + drive + "/" + "/".join(resolved.parts[1:])


def create_wsl_temp_dir() -> str:
    """Create a unique native WSL directory for compiler products."""

    result = subprocess.run(
        ["wsl.exe", "-d", "Debian", "--", "mktemp", "-d", "/tmp/v2-store-completion.XXXXXX"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    path = result.stdout.strip()
    if not path.startswith("/tmp/v2-store-completion."):
        raise RuntimeError(f"unexpected WSL temporary directory: {path!r}")
    return path


def remove_wsl_temp_dir(path: str) -> None:
    """Remove the exact temporary directory owned by this wave."""

    if not path.startswith("/tmp/v2-store-completion."):
        raise ValueError(f"refusing to remove unowned temporary path: {path}")
    subprocess.run(
        ["wsl.exe", "-d", "Debian", "--", "rm", "-rf", "--", path],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def run_verilator(source: Path, bench: Path, work_dir: str, label: str) -> dict[str, Any]:
    """Compile and run the locked or Amaranth source with identical vectors."""

    object_dir = f"{work_dir}/{label}_obj"
    binary = f"{work_dir}/{label}"
    compile_command = [
        "wsl.exe", "-d", "Debian", "--", "verilator", "--binary", "--timing",
        "--output-split", "2000", "--output-split-cfuncs", "200", "-CFLAGS", "-O0", "-j", "2",
        "-Wno-fatal", "-DSYNTHESIS", "--top-module", "tb", "--Mdir", object_dir,
        "-o", binary, wsl_path(source), wsl_path(bench),
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
    simulation_result = subprocess.run(
        simulation_command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if simulation_result.returncode != 0:
        raise RuntimeError(
            f"Verilator run failed for {source.name}:\n"
            f"{simulation_result.stdout}{simulation_result.stderr}"
        )
    samples = tuple(
        line.strip()
        for line in simulation_result.stdout.splitlines()
        if line.startswith("V:")
    )
    if not samples:
        raise RuntimeError(f"Verilator emitted no samples for {source.name}")
    return {
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "sample_sha256": hashlib.sha256("\n".join(samples).encode()).hexdigest(),
        "samples": samples,
        "compile": {
            "command": compile_command,
            "status": "PASS",
            "returncode": compile_result.returncode,
            "output_tail": (compile_result.stdout + compile_result.stderr)[-1000:],
        },
        "simulation": {
            "command": simulation_command,
            "status": "PASS",
            "returncode": simulation_result.returncode,
            "output_tail": simulation_result.stdout[-500:],
        },
    }


def verify_member(
    build: Any, member: str, work_dir: Path, wsl_work_dir: str
) -> dict[str, Any]:
    """Check ABI, deterministic export, and every output at every sample."""

    specs = tuple(build.PORT_SPECS[member])
    reference_path = REFERENCE_DIR / f"{member}.sv"
    reference_specs = parse_ports(reference_path.read_text(encoding="utf-8"), member)
    if not same_abi(specs, reference_specs):
        raise AssertionError(f"{member}: Build ABI differs from locked reference")
    exported = build.build_verilog({"module": member}, {})
    if exported != build.build_verilog({"module": member}, {}):
        raise AssertionError(f"{member}: nondeterministic Verilog export")
    if not same_abi(parse_ports(exported, member), reference_specs):
        raise AssertionError(f"{member}: exported ABI differs from locked reference")
    vectors = directed_vectors(member, specs)
    add_random_vectors(member, specs, vectors)
    bench = work_dir / f"{member}_tb.sv"
    dut_path = work_dir / f"{member}_amaranth.sv"
    bench.write_text(make_testbench(member, specs, vectors), encoding="utf-8", newline="\n")
    dut_path.write_text(exported, encoding="utf-8", newline="\n")
    reference = run_verilator(
        reference_path, bench, wsl_work_dir, f"{member}_reference"
    )
    candidate = run_verilator(dut_path, bench, wsl_work_dir, f"{member}_amaranth")
    reference_samples = reference["samples"]
    candidate_samples = candidate["samples"]
    mismatch: dict[str, Any] | None = None
    if reference_samples != candidate_samples:
        for index, (locked, dut) in enumerate(zip(reference_samples, candidate_samples)):
            if locked != dut:
                mismatch = {"sample_index": index, "locked": locked, "dut": dut}
                break
        if mismatch is None:
            mismatch = {
                "locked_sample_count": len(reference_samples),
                "dut_sample_count": len(candidate_samples),
            }
    output_names = [name for name, direction, _width in specs if direction == "output"]
    output_slices, output_chunks = output_slice_layout(specs)
    unknown = sum(
        any(character in token.lower() for character in "xz")
        for sample in reference_samples
        for token in sample.split()[1:]
    )
    status = "PASS_BOUNDED" if mismatch is None else "FAIL_BOUNDED"
    return {
        "status": status,
        "abi": {
            "status": "PASS",
            "port_count": len(specs),
            "input_count": sum(direction == "input" for _name, direction, _width in specs),
            "output_count": len(output_names),
            "ports": [
                {"name": name, "direction": direction, "width": width}
                for name, direction, width in sorted(specs)
            ],
            "build_matches_locked": True,
            "export_matches_locked": True,
            "deterministic_export": True,
        },
        "differential": {
            "status": status,
            "sample_count": len(reference_samples),
            "unknown_output_samples": unknown,
            "all_public_outputs_compared": True,
            "outputs_compared": output_names,
            "packed_output_slices": output_slices,
            "packed_output_chunk_count": len(output_chunks),
            "payloads_compared_when_valid_is_low": True,
            "resetless_startup_unclaimed": member in RESETLESS_STARTUP_OUTPUTS,
            "resetless_startup_outputs": list(RESETLESS_STARTUP_OUTPUTS[member]),
            "mismatch": mismatch,
            "reference": {
                "source_sha256": reference["source_sha256"],
                "sample_sha256": reference["sample_sha256"],
                "compile": reference["compile"],
                "simulation": reference["simulation"],
            },
            "amaranth": {
                "source_sha256": candidate["source_sha256"],
                "sample_sha256": candidate["sample_sha256"],
                "compile": candidate["compile"],
                "simulation": candidate["simulation"],
            },
        },
    }


def source_record(path: Path) -> dict[str, Any]:
    """Bind one source file to the non-counting receipt."""

    return {
        "path": path.resolve().relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def preparation_checks() -> dict[str, Any]:
    """Run source syntax, registered direct tests, isolated Pyright, and version probe."""

    compile_command = [
        sys.executable, "-B", "-m", "py_compile", str(BUILD), str(DIRECT), str(Path(__file__).resolve())
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
        sys.executable, "-B", str(DIRECT_RUNNER), "--test",
        DIRECT.relative_to(ROOT).as_posix(), "--minimum-tests", "7",
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
    direct_count = re.search(r"Ran\s+(\d+)\s+tests?", direct_output)
    pyright = subprocess.run(
        [
            sys.executable, "-B", "-c",
            "import sys,json; from pathlib import Path; "
            "sys.path.insert(0,'validation'); import v2_strict_family_rail as rail; "
            f"result=rail.pyright_check(Path({str(BUILD)!r})); "
            "print(json.dumps(result)); raise SystemExit(result['returncode'])",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    pyright_record = json.loads(pyright.stdout.strip().splitlines()[-1])
    verilator_command = ["wsl.exe", "-d", "Debian", "--", "verilator", "--version"]
    verilator = subprocess.run(
        verilator_command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if compile_result.returncode != 0:
        raise RuntimeError("py_compile failed: " + compile_result.stderr)
    if direct_result.returncode != 0 or direct_count is None or int(direct_count.group(1)) < 7:
        raise RuntimeError("direct tests failed or were not discovered:\n" + direct_output[-2500:])
    if pyright.returncode != 0 or pyright_record.get("status") != "PASS":
        raise RuntimeError("isolated Pyright failed: " + pyright.stdout + pyright.stderr)
    if verilator.returncode != 0:
        raise RuntimeError("Verilator version probe failed: " + verilator.stderr)
    return {
        "py_compile": {"command": compile_command, "status": "PASS", "returncode": 0},
        "direct_test": {
            "command": direct_command,
            "status": "PASS",
            "returncode": direct_result.returncode,
            "tests_run": int(direct_count.group(1)),
            "output_tail": direct_output[-1600:],
        },
        "pyright": pyright_record,
        "verilator": {
            "command": verilator_command,
            "status": "PASS",
            "returncode": verilator.returncode,
            "version": verilator.stdout.strip(),
        },
    }


def main() -> int:
    """Run the complete family and write a source-bound, non-counting receipt."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--member", choices=MEMBERS, action="append")
    parser.add_argument("--evidence", help="Optional distinct focused receipt filename under validation")
    args = parser.parse_args()
    selected = tuple(args.member or MEMBERS)
    complete_run = set(selected) == set(MEMBERS)
    evidence = EVIDENCE
    if args.evidence:
        if Path(args.evidence).name != args.evidence or "strict-evidence" in args.evidence:
            raise ValueError("focused receipts must be distinct validation filenames")
        evidence = ROOT / "validation" / args.evidence
    build = load_build()
    preparation = preparation_checks() if complete_run else {}
    member_results: dict[str, Any] = {}
    failures: list[str] = []
    wsl_work_dir = create_wsl_temp_dir()
    try:
        with tempfile.TemporaryDirectory(prefix="v2_store_completion_wave_") as directory:
            work_dir = Path(directory)
            for member in selected:
                try:
                    result = verify_member(build, member, work_dir, wsl_work_dir)
                except Exception as error:  # retain each member's independent diagnostic
                    result = {"status": "FAIL_TOOL_OR_VALIDATION", "error": str(error)}
                member_results[member] = result
                if result["status"] != "PASS_BOUNDED":
                    failures.append(member)
    finally:
        remove_wsl_temp_dir(wsl_work_dir)

    status = "PASS_BOUNDED" if complete_run and not failures else (
        "FAIL_BOUNDED" if complete_run else "FOCUSED_DIAGNOSTIC_PASS" if not failures else "FOCUSED_DIAGNOSTIC_FAIL"
    )
    if complete_run or args.evidence:
        payload = {
            "schema_version": 1,
            "kind": "XIANGSHAN_KUNMINGHU_V2_STORE_COMPLETION_WAVE",
            "full_family_run": complete_run,
            "selected_members": list(selected),
            "build_id": "Build-Cpu.Memory.Store.Family",
            "direct_test_id": "Build-Cpu.Memory.Store.Family",
            "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
            "status": status,
            "strict_complete_build_count_delta": 0,
            "acceptance_eligible": False,
            "formal_run": False,
            "sources": {
                "python_build": source_record(BUILD),
                "direct_test": source_record(DIRECT),
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
            "failures": failures,
            "unclosed": [
                "StoreMisalignBuffer transformation, replay, 4KB split, exception and vector writeback behavior remain pending if differential is not exact.",
                "StoreUnit pipeline, DTLB/PMP/DCache, redirect, nuke, prefetch, vector and exception behavior remain pending if differential is not exact.",
                "Reset-less startup state is explicitly unclaimed for all family members.",
                "Formal equivalence, parent closure, license review and acceptance remain pending.",
            ],
        }
        evidence.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"Receipt: {evidence.relative_to(ROOT).as_posix()}")
    for member, result in member_results.items():
        differential = result.get("differential", {})
        detail = result.get("error") or differential.get("mismatch")
        print(
            f"{member}: {result['status']} "
            f"ports={result.get('abi', {}).get('port_count', 'n/a')} "
            f"outputs={result.get('abi', {}).get('output_count', 'n/a')} "
            f"samples={differential.get('sample_count', 'n/a')} "
            f"detail={str(detail)[:1200]}"
        )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
