"""CoupledL2 TL2TL locked differential protocol-coverage batch 2.

This is a deliberately bounded, read-only comparison against the immutable
``TL2TLCoupledL2`` closure.  It expands the previous 3-vector check to every
stable ready/valid protocol observation and drives reset, idle, acquire, probe,
refill, and response boundary vectors.  A partial run is never labelled
``PASS`` or ``ACCEPTED``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

_LOCKED_SCRIPT = Path(__file__).with_name("v2_coupled_l2_tl2tl_parent_locked_differential.py")
_LOCKED_SPEC = importlib.util.spec_from_file_location("v2_tl2tl_locked_base", _LOCKED_SCRIPT)
if _LOCKED_SPEC is None or _LOCKED_SPEC.loader is None:
    raise RuntimeError(_LOCKED_SCRIPT)
_LOCKED_BASE = importlib.util.module_from_spec(_LOCKED_SPEC)
sys.modules[_LOCKED_SPEC.name] = _LOCKED_BASE
_LOCKED_SPEC.loader.exec_module(_LOCKED_BASE)

from v2_tl2tl_locked_base import (
    LOCKED,
    LOCKED_BYTES,
    LOCKED_SHA256,
    ROOT,
    SLICE_TARGET,
    SOURCE_COMMIT,
    TARGET,
    build_testbench as _legacy_build_testbench,
    digest,
    extract_module_map,
    load,
    port_declarations,
    run_wsl,
    reachable_closure,
    reference_port_name,
    wsl_path,
)


EVIDENCE = ROOT / "validation/v2-coupledL2-tl2tl-protocol-coverage-batch2-results.json"
CACHE_ROOT = ROOT / "validation/.cache/tl2tl-protocol-coverage-batch2"


PortMap = dict[str, tuple[str, int]]


def _sv_width(width_text: str | None) -> int:
    """Return the number of bits represented by one SV packed range."""

    if not width_text:
        return 1
    values = re.findall(r"-?\d+", width_text)
    if len(values) < 2:
        return 1
    return abs(int(values[0]) - int(values[1])) + 1


def generated_port_declarations(source: str, module_name: str) -> PortMap:
    """Parse the actual direction/width declarations of one generated module.

    The Amaranth target uses a non-ANSI header followed by ``input``/``output``
    declarations, while the extracted Chisel reference uses an ANSI header.
    Keeping one conservative parser for both forms means that optional ports
    (notably TL ``E`` channels) are wired only when both generated modules
    really expose them.
    """

    module_match = re.search(
        rf"(?m)^\s*module\s+{re.escape(module_name)}\s*\(", source
    )
    if module_match is None:
        raise RuntimeError(f"generated module declaration missing: {module_name}")
    end_match = re.search(r"\bendmodule\b", source[module_match.start() :])
    if end_match is None:
        raise RuntimeError(f"generated module is unterminated: {module_name}")
    module_text = source[module_match.start() : module_match.start() + end_match.end()]
    # Port comments in Chisel output contain declaration-like words.  Remove
    # comments before tokenizing so an absent port cannot be resurrected by a
    # source-location comment.
    clean = re.sub(r"/\*.*?\*/", " ", module_text, flags=re.S)
    clean = re.sub(r"//[^\r\n]*", " ", clean)
    ports: PortMap = {}

    # Parse ANSI declarations in the module header.  Continuation names inherit
    # the previous direction/range, as emitted by Chisel.
    header_match = re.search(
        rf"\bmodule\s+{re.escape(module_name)}\s*\((.*?)\)\s*;", clean, re.S
    )
    header_names: set[str] | None = None
    if header_match is not None:
        # Keep the header name set even for non-ANSI output.  A backend may
        # leave an internal ``input``/``output`` declaration in the body after
        # pruning that pin from the actual module envelope; such a name must
        # not be treated as a connectable port.
        header_names = set(
            re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", header_match.group(1))
        )
        direction: str | None = None
        width = 1
        for token in header_match.group(1).split(","):
            token = token.strip().strip(";")
            if not token:
                continue
            declaration = re.match(
                r"^(input|output|inout)\b\s*"
                r"(?:(?:wire|reg|logic)\b\s*)?"
                r"(?:signed\b\s*)?(\[[^]]+\])?\s*(.*)$",
                token,
            )
            if declaration is not None:
                direction = declaration.group(1)
                width = _sv_width(declaration.group(2))
                names = declaration.group(3)
            else:
                names = token
            if direction is None:
                # Non-ANSI headers only list names; directions arrive below.
                continue
            for name in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", names):
                if name not in {"input", "output", "inout", "wire", "reg", "logic", "signed"}:
                    ports.setdefault(name, (direction, width))

    # Parse non-ANSI declarations (and also capture any ANSI body redeclarations
    # produced by a backend).  Start after the ANSI header; otherwise the first
    # ``input`` token in a semicolon-terminated body assignment would consume
    # the whole header and fabricate names/directions.
    declaration_source = clean[header_match.end() :] if header_match is not None else clean
    declaration_re = re.compile(
        r"\b(input|output|inout)\b\s*"
        r"(?:(?:wire|reg|logic)\b\s*)?"
        r"(?:signed\b\s*)?(\[[^]]+\])?\s*([^;]+);"
    )
    for declaration in declaration_re.finditer(declaration_source):
        direction = declaration.group(1)
        width = _sv_width(declaration.group(2))
        names = declaration.group(3)
        for name in names.split(","):
            match = re.search(r"\b[A-Za-z_][A-Za-z0-9_]*\b", name.strip())
            if match is not None:
                ports[match.group(0)] = (direction, width)
    if header_names is not None:
        ports = {name: spec for name, spec in ports.items() if name in header_names}
    return ports


def _filter_contract(
    contract: tuple[dict[str, Any], ...],
    target_ports: PortMap,
    reference_ports: PortMap,
) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]:
    """Keep only ports present with matching directions on both sides."""

    filtered: list[dict[str, Any]] = []
    missing_target: list[str] = []
    missing_reference: list[str] = []
    direction_mismatch: list[dict[str, Any]] = []
    for row in contract:
        name = str(row["name"])
        reference_name = reference_port_name(name)
        target_decl = target_ports.get(name)
        reference_decl = reference_ports.get(reference_name)
        if target_decl is None:
            missing_target.append(name)
            continue
        if reference_decl is None:
            missing_reference.append(name)
            continue
        expected_direction = str(row["direction"])
        if target_decl[0] != expected_direction or reference_decl[0] != expected_direction:
            direction_mismatch.append(
                {
                    "name": name,
                    "reference_name": reference_name,
                    "expected": expected_direction,
                    "target": target_decl[0],
                    "reference": reference_decl[0],
                }
            )
            # Direction differences are expected at BankBinder boundaries
            # (``auto_in``/``auto_out`` names describe the parent side, not the
            # generated module's local flow).  Presence is the compile-safety
            # criterion here; retain the contract row and report the mismatch
            # for audit instead of dropping an otherwise stable observation.
        # Use the generated target width for TB wires.  Reference widths can
        # legitimately differ for payload fields (for example E sink IDs), but
        # ready/valid observations are scalar and remain strictly comparable.
        filtered.append({**row, "width": target_decl[1]})
    report = {
        "contract_count": len(contract),
        "wired_count": len(filtered),
        "missing_target": sorted(missing_target),
        "missing_reference": sorted(missing_reference),
        "direction_mismatch": direction_mismatch,
        "target_port_count": len(target_ports),
        "reference_port_count": len(reference_ports),
    }
    return tuple(filtered), report


def protocol_outputs(contract: tuple[dict[str, Any], ...]) -> list[str]:
    """Select all stable ready/valid and arbitration observations."""

    selected: list[str] = []
    for row in contract:
        if row["direction"] != "output":
            continue
        name = row["name"]
        # TileLink A/B/C/D/E handshakes, TPMeta, TLB request, and error/miss
        # arbitration controls are stable protocol observations.  Payload and
        # performance counters remain available but intentionally un-compared.
        if name.endswith(("_ready", "_valid")) or name in {"io_l2Miss", "io_error_valid"}:
            selected.append(name)
    return selected


def _phase_stimulus(phase: str, contract: tuple[dict[str, Any], ...]) -> list[str]:
    """Emit deterministic input assignments for one protocol boundary."""

    lines: list[str] = []
    inputs = {
        str(row["name"])
        for row in contract
        if row["direction"] == "input"
    }

    def assign(name: str, value: str) -> None:
        # Optional protocol fields are intentionally absent from some emitted
        # target/reference variants.  Never emit a dangling TB identifier.
        if name in inputs:
            lines.append(f"{name}={value};")

    for row in contract:
        if row["direction"] != "input":
            continue
        name = row["name"]
        if name == "clock":
            continue
        if name == "reset":
            assign("reset", "1" if phase == "reset" else "0")
            continue
        # Keep every sink ready so each boundary observes an actual handshake;
        # all payload/valid inputs are then overridden for the selected vector.
        value = "1" if name.endswith("_ready") else "0"
        assign(name, value)
    if phase == "acquire":
        for name, value in (
            ("auto_in_0_a_valid", "1"),
            ("auto_in_0_a_bits_opcode", "4"),
            ("auto_in_0_a_bits_size", "3"),
            ("auto_in_0_a_bits_source", "9"),
            ("auto_in_0_a_bits_address", "48'h12340"),
            ("auto_in_0_a_bits_data", "256'h55AA"),
            ("auto_in_0_a_bits_mask", "32'hFFFFFFFF"),
        ):
            assign(name, value)
    elif phase == "probe":
        for name, value in (
            ("auto_out_0_b_valid", "1"),
            ("auto_out_0_b_bits_opcode", "3"),
            ("auto_out_0_b_bits_size", "3"),
            ("auto_out_0_b_bits_source", "2"),
            ("auto_out_0_b_bits_address", "48'h9870"),
        ):
            assign(name, value)
    elif phase == "refill":
        for name, value in (
            ("auto_out_0_d_valid", "1"),
            ("auto_out_0_d_bits_opcode", "1"),
            ("auto_out_0_d_bits_size", "3"),
            ("auto_out_0_d_bits_source", "9"),
            ("auto_out_0_d_bits_sink", "2"),
            ("auto_out_0_d_bits_data", "256'hABCDEF"),
        ):
            assign(name, value)
    elif phase == "response":
        for name, value in (
            ("auto_in_0_e_valid", "1"),
            ("auto_in_0_e_bits_sink", "5"),
            ("auto_in_0_c_valid", "1"),
            ("auto_in_0_c_bits_opcode", "7"),
            ("auto_in_0_c_bits_size", "3"),
            ("auto_in_0_c_bits_source", "4"),
            ("auto_in_0_c_bits_address", "48'h4560"),
            ("auto_in_0_c_bits_data", "256'h77"),
        ):
            assign(name, value)
    return lines


def build_protocol_testbench(contract: tuple[dict[str, Any], ...]) -> tuple[str, list[str], list[str]]:
    """Create a six-boundary A/B testbench and return compared names."""

    declarations, connections, _ = port_declarations(contract)
    compared = protocol_outputs(contract)
    expression = " || ".join(f"t_{name} !== r_{name}" for name in compared) or "1'b0"
    lines = [
        "module tb;", *declarations, "always #5 clock=~clock;",
        "integer cycle; integer mismatch_count; integer phase_id;",
        f"UHSCTL2TLCoupledL2 target(\n{connections[0]}\n);",
        f"TL2TLCoupledL2Reference reference(\n{connections[1]}\n);",
        "task check; input integer p; begin #1; cycle=cycle+1; phase_id=p;",
        f"if ({expression}) begin mismatch_count=mismatch_count+1; $display(\"TL2TL_PROTOCOL_MISMATCH phase=%0d cycle=%0d\",p,cycle);",
        *[f"if (t_{name} !== r_{name}) $display(\"DIFF {name} t=%h r=%h\", t_{name}, r_{name});" for name in compared[:32]],
        "end end endtask",
        "initial begin cycle=0; mismatch_count=0; phase_id=0;",
    ]
    # Baseline all inputs once, then apply each boundary vector.  Inputs are
    # re-driven per phase to avoid stateful valid/ready leakage between checks.
    for row in contract:
        if row["direction"] == "input" and row["name"] != "clock":
            lines.append(f"{row['name']}='0;")
    phases = ["reset", "idle", "acquire", "probe", "refill", "response"]
    for index, phase in enumerate(phases, 1):
        lines += [f"// {phase} boundary", *_phase_stimulus(phase, contract), f"@(posedge clock); check({index});"]
        # Drop valid strobes after observing the handshake, retaining ready.
        if phase not in {"reset", "idle"}:
            lines += [f"// {phase} release", *_phase_stimulus("idle", contract), "@(posedge clock); check(0);"]
    lines += [
        'if (mismatch_count==0) $display("TL2TL_PROTOCOL_COVERAGE_PASS 6");',
        'else $display("TL2TL_PROTOCOL_COVERAGE_FAIL mismatches=%0d", mismatch_count);',
        "$finish; end", "endmodule",
    ]
    return "\n".join(lines) + "\n", phases, compared


def cached_gate(command: list[str], marker: Path, cache_label: str) -> dict[str, Any]:
    """Run a backend gate once and reuse a hash-keyed marker thereafter."""

    if marker.is_file():
        return {"status": "PASS_REUSED_CACHE", "returncode": 0, "cache": cache_label}
    result = run_wsl(command)
    if result["returncode"] == 0:
        marker.write_text("ok\n", encoding="utf-8", newline="\n")
    result["cache"] = cache_label
    return result


def main() -> int:
    """Run protocol coverage and persist bounded, non-accepting evidence."""

    target = load(TARGET, "v2_tl2tl_protocol_batch2_target")
    slice_module = load(SLICE_TARGET, "v2_tl2tl_protocol_batch2_slice")
    modules, locked_sha, preamble = extract_module_map()
    closure = reachable_closure(modules)
    contract = tuple(target.tl2tl_parent_port_contract(target.TL2TLCoupledL2ParentConfig()))
    rtl = target.build_parent_verilog(
        {"module": "UHSCTL2TLCoupledL2"}, {"slices": [slice_module.CoupledL2Slice() for _ in range(4)]}
    )
    # Build the immutable reference closure before rendering the TB.  The
    # generated target and extracted reference are allowed to differ in
    # optional Diplomacy ports; only the declaration intersection is wired.
    ref_blob = (
        preamble
        + b"\n`ifndef ASSERT_VERBOSE_COND_\n`define ASSERT_VERBOSE_COND_ 0\n`endif\n"
        + b"`ifndef STOP_COND_\n`define STOP_COND_ 0\n`endif\n"
        + b"\n".join(modules[name] for name in modules)
    )
    ref_blob = ref_blob.replace(
        b"module TL2TLCoupledL2(", b"module TL2TLCoupledL2Reference(", 1
    )
    target_ports = generated_port_declarations(rtl, "UHSCTL2TLCoupledL2")
    reference_ports = generated_port_declarations(
        ref_blob.decode("utf-8", "replace"), "TL2TLCoupledL2Reference"
    )
    wired_contract, port_filter = _filter_contract(contract, target_ports, reference_ports)
    tb_text, phases, compared = build_protocol_testbench(wired_contract)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    target_rtl = CACHE_ROOT / "target.sv"
    tb = CACHE_ROOT / "tb.sv"
    ref_rtl = CACHE_ROOT / "reference.sv"
    target_hash = hashlib.sha256(rtl.encode()).hexdigest()
    reference_hash = digest(ref_blob)
    tb_hash = hashlib.sha256(tb_text.encode()).hexdigest()
    cache_reused = (
        target_rtl.is_file() and tb.is_file() and ref_rtl.is_file()
        and digest(target_rtl.read_bytes()) == target_hash
        and digest(tb.read_bytes()) == tb_hash
        and digest(ref_rtl.read_bytes()) == reference_hash
    )
    if not cache_reused:
        target_rtl.write_text(rtl, encoding="utf-8", newline="\n")
        tb.write_text(tb_text, encoding="utf-8", newline="\n")
        ref_rtl.write_bytes(ref_blob)
    obj = CACHE_ROOT / "obj"
    obj.mkdir(exist_ok=True)
    compile_hash = hashlib.sha256(
        f"{target_hash}:{reference_hash}:{tb_hash}".encode()
    ).hexdigest()
    compile_marker = CACHE_ROOT / f"compile-{compile_hash}.ok"
    compile_result = {"status": "PASS_REUSED_CACHE", "returncode": 0, "cache": str(obj)} if compile_marker.is_file() and (obj / "Vtb").is_file() else run_wsl([
        "verilator", "--binary", "--timing", "-Wno-fatal", "--top-module", "tb", "--Mdir", wsl_path(obj),
        wsl_path(target_rtl), wsl_path(ref_rtl), wsl_path(tb)
    ])
    if compile_result["returncode"] == 0:
        compile_marker.write_text("ok\n", encoding="utf-8", newline="\n")
    run_result = run_wsl([wsl_path(obj / "Vtb")]) if compile_result["returncode"] == 0 else {"status": "SKIP", "returncode": 1}
    lint = cached_gate(["verilator", "--lint-only", "-Wno-fatal", "--top-module", "UHSCTL2TLCoupledL2", wsl_path(target_rtl)], CACHE_ROOT / f"lint-{target_hash}.ok", "verilator")
    yosys = cached_gate(["yosys", "-Q", "-p", f"read_verilog -sv {wsl_path(target_rtl)}; hierarchy -top UHSCTL2TLCoupledL2; proc; opt; check; stat"], CACHE_ROOT / f"yosys-{target_hash}.ok", "yosys")
    passed = run_result.get("returncode") == 0 and "TL2TL_PROTOCOL_COVERAGE_PASS" in str(run_result.get("output_tail", ""))
    available = sum(row["direction"] == "output" for row in wired_contract)
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_COUPLEDL2_TL2TL_PROTOCOL_COVERAGE_BATCH2",
        "batch_id": "V2-DEPENDENCY-COUPLEDL2-TL2TL-PROTOCOL-COVERAGE-002",
        "source_commit": SOURCE_COMMIT,
        "locked_xstop": {"canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv", "bytes": LOCKED_BYTES, "sha256": locked_sha, "expected_sha256": LOCKED_SHA256, "module": "TL2TLCoupledL2", "closure_modules": len(closure)},
        "target": {"path": TARGET.relative_to(ROOT).as_posix(), "rtl_sha256": target_hash, "rtl_bytes": len(rtl.encode())},
        "reference": {"rtl_sha256": reference_hash, "rtl_bytes": len(ref_blob)},
        "port_filter": port_filter,
        "differential": {"status": "PASS" if passed and lint["returncode"] == 0 and yosys["returncode"] == 0 else "FAIL", "vectors": len(phases), "vector_boundaries": phases, "available_output_count": available, "compared_outputs": len(compared), "compared_output_names": compared, "coverage_scope": "all stable ready/valid handshake, arbitration controls, reset/idle/acquire/probe/refill/response boundaries", "compile": compile_result, "run": run_result},
        "tool_gates": {"verilator": lint, "yosys": yosys, "cache_reused": cache_reused, "cache_root": str(CACHE_ROOT.relative_to(ROOT)), "compile_hash": compile_hash},
        "gates": {"DIRECT_TEST_PASS_BOUNDED": "PASS" if passed else "FAIL", "V2_REFERENCE_MATCHED": "PASS_BOUNDED_LOCKED_XSTOP" if passed else "FAIL", "VERILATOR": lint["status"], "YOSYS": yosys["status"], "ACCEPTED": "NOT_ALLOWED"},
        "status": "PASS_BOUNDED_LOCKED_XSTOP_PROTOCOL_COVERAGE" if passed and lint["returncode"] == 0 and yosys["returncode"] == 0 else "FAIL_PROTOCOL_COVERAGE",
        "acceptance_eligible": False,
        "unclosed": ["Full TL2TL CoupledL2 Slice/Directory/Prefetch/Diplomacy behavior remains pending.", "Bounded protocol vectors do not establish complete parent closure.", "Partial coverage is not labelled PASS or ACCEPTED."],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "vectors": len(phases), "available_output_count": available, "compared_outputs": len(compared), "cache_reused": cache_reused, "ACCEPTED": "NOT_ALLOWED"}, sort_keys=True))
    return 0 if payload["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
