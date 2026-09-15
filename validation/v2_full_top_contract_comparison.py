"""Reproducible full-top V2 contract comparison.

可复用的 V2 完整顶层合约对比。

The local ``UHSCTop`` and source-named ``XSTop`` implementations currently
provide exact external envelopes, not a complete executable Kunminghu V2
closure.  This validator therefore separates four facts which must not be
conflated:

* the immutable locked XSTop header and frozen inventory agree;
* both local envelopes preserve every top-level port's name, direction, and
  width, including AXI-style valid/ready orientation;
* the present local top can be directly simulated only as its documented
  diagnostic/quiescent envelope, then linted and synthesized; and
* a behavioral differential against the locked XSTop remains pending until
  the child closures and executable reference assembly exist.

It deliberately does *not* compare flat generated module names.  Amaranth
hierarchical names and Chisel flattened names are not an instance-normalized
functional equivalence relation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, cast

from amaranth.sim import Settle, Simulator


ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "validation"
WORK = VALIDATION / ".work" / "v2-full-top-contract"
TOP_BUILD = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Top.UHSCTop-GenerationProbe-Hardware.py"
ROOT_BUILD = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Top.XiangShan-Roots-Hardware.py"
INVENTORY = VALIDATION / "v2-xstop-port-inventory.json"
NORMALIZED_METRICS = VALIDATION / "v2-top-generation-normalized-metrics.json"
OUTPUT = VALIDATION / "v2-full-top-contract-comparison-results.json"

DEFAULT_XSTOP = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
WSL_XSTOP = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
EXPECTED_XSTOP_BYTES = 228590583
EXPECTED_XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
EXPECTED_SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"

MODULE_LINE = re.compile(rb"^module\s+XSTop\s*\(")
COMMENT = re.compile(r"//.*$")
GENERATED_PORT = re.compile(
    r"^\s*(input|output|inout)(?:\s+(?:wire|reg|logic))?"
    r"(?:\s+\[([0-9]+):([0-9]+)\])?\s+(.+?);\s*$"
)
HANDSHAKE_PORT = re.compile(
    r"^(?P<bus>[A-Za-z0-9_]+)_(?P<channel>aw|w|b|ar|r)(?P<role>valid|ready)$"
)


def digest_file(path: Path) -> str:
    """Hash a file without loading the 228 MB reference into memory."""

    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def width_from_text(value: object) -> int:
    """Normalize a frozen Verilog range to an unsigned bit count."""

    text = str(value or "").strip()
    if not text:
        return 1
    match = re.fullmatch(r"\[\s*([0-9]+)\s*:\s*([0-9]+)\s*\]", text)
    if match is None:
        raise ValueError(f"unsupported fixed port width: {value!r}")
    return abs(int(match.group(1)) - int(match.group(2))) + 1


def normalize_port(port: Mapping[str, object]) -> dict[str, object]:
    name = str(port.get("name", "")).strip()
    direction = str(port.get("direction", "")).strip().lower()
    if not name or direction not in {"input", "output", "inout"}:
        raise ValueError(f"invalid port record: {port!r}")
    return {"name": name, "direction": direction, "width": width_from_text(port.get("width", ""))}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def capture_xstop_header(path: Path) -> bytes:
    """Stream the immutable reference and capture only the XSTop header."""

    active = False
    lines: list[bytes] = []
    with path.open("rb") as stream:
        for line in stream:
            if not active:
                if MODULE_LINE.match(line):
                    active = True
                    terminator = line.find(b");")
                    if terminator >= 0:
                        lines.append(line[: terminator + 2])
                        return b"".join(lines)
                    lines.append(line)
                continue
            terminator = line.find(b");")
            if terminator >= 0:
                lines.append(line[: terminator + 2])
                return b"".join(lines)
            lines.append(line)
    raise RuntimeError("XSTop ANSI header not found in locked reference")


def parse_ansi_header(header: bytes) -> list[dict[str, object]]:
    """Parse the pinned Chisel ANSI header conservatively and deterministically."""

    ports: list[dict[str, object]] = []
    direction = ""
    width = ""
    for raw_line in header.decode("utf-8", "replace").splitlines():
        line = COMMENT.sub("", raw_line).strip()
        if not line:
            continue
        if line.startswith("module "):
            line = line[line.find("(") + 1 :]
        if line.endswith(");"):
            line = line[:-2]
        elif line.endswith(")"):
            line = line[:-1]
        for part in line.split(","):
            token = part.strip().strip(")").strip()
            if not token:
                continue
            match = re.match(r"^(input|output|inout)\s+(?:(\[[^]]+\])\s*)?(.*)$", token)
            if match is not None:
                direction = match.group(1)
                width = match.group(2) or ""
                names = match.group(3).strip()
            else:
                names = token
            for name in re.findall(r"[A-Za-z_][A-Za-z0-9_$]*", names):
                if name not in {"input", "output", "inout", "wire", "reg", "logic"}:
                    ports.append({"name": name, "direction": direction, "width": width_from_text(width)})
    unique: list[dict[str, object]] = []
    seen: set[str] = set()
    for port in ports:
        name = str(port["name"])
        if name not in seen:
            unique.append(port)
            seen.add(name)
    return unique


def module_body(text: str, module_name: str) -> str:
    start = re.search(rf"(?m)^module\s+{re.escape(module_name)}\s*\(", text)
    if start is None:
        raise RuntimeError(f"module {module_name} not found")
    end = re.search(r"(?m)^endmodule\b", text[start.end() :])
    if end is None:
        raise RuntimeError(f"endmodule for {module_name} not found")
    return text[start.start() : start.end() + end.end()]


def parse_generated_ports(text: str, module_name: str) -> list[dict[str, object]]:
    """Read generated non-ANSI declarations, ignoring duplicated wire lines."""

    ports: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in module_body(text, module_name).splitlines():
        match = GENERATED_PORT.match(line)
        if match is None:
            continue
        direction, high, low, names = match.groups()
        width = abs(int(high) - int(low)) + 1 if high is not None and low is not None else 1
        for raw_name in names.split(","):
            name = raw_name.strip().lstrip("\\").strip()
            if name and name not in seen:
                ports.append({"name": name, "direction": direction, "width": width})
                seen.add(name)
    return ports


def schema_comparison(reference: Iterable[Mapping[str, object]], candidate: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """Compare named port maps; order is intentionally not a behavioral gate."""

    expected = {
        str(port["name"]): (str(port["direction"]), int(cast(int, port["width"])))
        for port in reference
    }
    actual = {
        str(port["name"]): (str(port["direction"]), int(cast(int, port["width"])))
        for port in candidate
    }
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    mismatches = [
        {
            "name": name,
            "reference": {"direction": expected[name][0], "width": expected[name][1]},
            "candidate": {"direction": actual[name][0], "width": actual[name][1]},
        }
        for name in sorted(set(expected) & set(actual))
        if expected[name] != actual[name]
    ]
    return {
        "reference_port_count": len(expected),
        "candidate_port_count": len(actual),
        "exact_direction_width_matches": len(expected) - len(missing) - len(mismatches),
        "missing": missing,
        "extra": extra,
        "direction_width_mismatches": mismatches,
        "status": "PASS" if not missing and not extra and not mismatches else "FAIL",
        "port_order": "NOT_A_GATE_NAMED_PORT_CONTRACT",
    }


def handshake_contract(reference: Iterable[Mapping[str, object]], candidate: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """Check AXI-style valid/ready pairs and their external orientation."""

    def pairs(ports: Iterable[Mapping[str, object]]) -> dict[str, dict[str, tuple[str, int]]]:
        result: dict[str, dict[str, tuple[str, int]]] = {}
        for port in ports:
            match = HANDSHAKE_PORT.match(str(port["name"]))
            if match is None:
                continue
            key = f"{match.group('bus')}_{match.group('channel')}"
            result.setdefault(key, {})[match.group("role")] = (
                str(port["direction"]),
                int(cast(int, port["width"])),
            )
        return result

    expected = pairs(reference)
    actual = pairs(candidate)
    issues: list[dict[str, object]] = []
    records: list[dict[str, object]] = []
    for key in sorted(set(expected) | set(actual)):
        ref = expected.get(key, {})
        got = actual.get(key, {})
        record: dict[str, object] = {"channel": key, "reference": ref, "candidate": got}
        missing_roles = sorted(set(ref) - set(got))
        extra_roles = sorted(set(got) - set(ref))
        if missing_roles or extra_roles:
            record["status"] = "FAIL"
            record["missing_roles"] = missing_roles
            record["extra_roles"] = extra_roles
            issues.append(record)
            records.append(record)
            continue
        ref_pair = ref.get("valid"), ref.get("ready")
        got_pair = got.get("valid"), got.get("ready")
        if all(item is not None and item[1] == 1 for item in (*ref_pair, *got_pair)):
            ref_valid = cast(tuple[str, int], ref_pair[0])
            ref_ready = cast(tuple[str, int], ref_pair[1])
            got_valid = cast(tuple[str, int], got_pair[0])
            got_ready = cast(tuple[str, int], got_pair[1])
            well_formed = True
            opposite = ref_valid[0] != ref_ready[0] and got_valid[0] != got_ready[0]
        else:
            well_formed = False
            opposite = False
        exact = ref_pair == got_pair
        record["status"] = "PASS" if well_formed and opposite and exact else "FAIL"
        record["orientation"] = "OPPOSITE_EXTERNAL_DIRECTIONS" if opposite else "INVALID"
        if record["status"] != "PASS":
            issues.append(record)
        records.append(record)
    return {
        "reference_channel_count": len(expected),
        "candidate_channel_count": len(actual),
        "checked_channels": len(records),
        "channels": records,
        "issues": issues,
        "status": "PASS" if records and not issues else "FAIL",
        "scope": "AXI_STYLE_VALID_READY_ONLY",
    }


def load_build(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_text(path: Path, text: str) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "bytes": len(text.encode("utf-8")),
        "sha256": digest_text(text),
    }


def render_reference_carrier(module_name: str, ports: Iterable[Mapping[str, object]]) -> str:
    """Build a lintable carrier from the *actual locked header* only.

    The carrier is intentionally a port-contract artifact, not a behavioral
    replacement for XSTop.  It lets both tools validate the same 204-port
    declaration as the target while raw XSTop still needs its resource-file
    assembly.
    """

    rows: list[dict[str, Any]] = [dict(cast(Mapping[str, Any], port)) for port in ports]
    lines = [f"module {module_name}("]
    for index, port in enumerate(rows):
        width = int(port["width"])
        range_text = "" if width == 1 else f" [{width - 1}:0]"
        comma = "," if index + 1 < len(rows) else ""
        lines.append(f"  {port['direction']}{range_text} {port['name']}{comma}")
    lines.append(");")
    for port in rows:
        if port["direction"] == "output":
            width = int(port["width"])
            if width == 1:
                lines.append(f"  assign {port['name']} = 1'b0;")
            else:
                lines.append(f"  assign {port['name']} = {width}'b0;")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def windows_to_wsl(path: Path) -> str:
    resolved = str(path.resolve())
    normalized = resolved.replace("\\", "/")
    if len(normalized) >= 3 and normalized[1] == ":" and normalized[2] == "/":
        return f"/mnt/{normalized[0].lower()}{normalized[2:]}"
    if normalized.startswith("//wsl$/Debian/"):
        return "/" + normalized.split("/Debian/", 1)[1]
    raise RuntimeError(f"cannot translate path to WSL: {path}")


def tail(value: str | bytes | None, limit: int = 3000) -> str:
    """Return a bounded text tail, decoding timeout payloads when needed."""

    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    return value[-limit:]


def run_wsl(command: str, timeout_seconds: int = 180) -> dict[str, object]:
    wsl = shutil.which("wsl.exe")
    if wsl is None:
        return {"status": "UNAVAILABLE", "reason": "wsl.exe not found", "command": command}
    try:
        result = subprocess.run(
            [wsl, "-e", "bash", "-lc", command],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        return {
            "status": "TIMEOUT",
            "timeout_seconds": timeout_seconds,
            "command": command,
            "stdout_tail": tail(error.stdout or ""),
            "stderr_tail": tail(error.stderr or ""),
        }
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "command": command,
        "stdout_tail": tail(result.stdout),
        "stderr_tail": tail(result.stderr),
    }


def run_tools(path: Path, top_module: str) -> dict[str, dict[str, object]]:
    source = windows_to_wsl(path)
    verilator_command = (
        f"verilator --lint-only --Wno-fatal --top-module {shlex.quote(top_module)} {shlex.quote(source)}"
    )
    yosys_program = f"read_verilog -sv {source}; hierarchy -check -top {top_module}; proc; check"
    yosys_command = f"yosys -Q -p {shlex.quote(yosys_program)}"
    return {
        "verilator": run_wsl(verilator_command),
        "yosys": run_wsl(yosys_command),
    }


def raw_reference_tool_probe() -> dict[str, object]:
    """Record why the raw locked artifact cannot itself be an executable DUT."""

    verilator = run_wsl(
        f"verilator --lint-only --Wno-fatal --top-module XSTop {shlex.quote(WSL_XSTOP)}",
        timeout_seconds=180,
    )
    yosys_program = f"read_verilog -sv {WSL_XSTOP}; hierarchy -check -top XSTop"
    yosys = run_wsl(f"yosys -Q -p {shlex.quote(yosys_program)}", timeout_seconds=180)

    def classify(tool: str, record: Mapping[str, object]) -> str:
        if record.get("status") == "PASS":
            return "PASS"
        text = f"{record.get('stdout_tail', '')}\n{record.get('stderr_tail', '')}"
        if tool == "verilator" and "ClockGate.sv" in text:
            return "PENDING_REFERENCE_RESOURCE_FILELIST_ASSEMBLY"
        if tool == "yosys" and "TOK_AUTOMATIC" in text:
            return "PENDING_REFERENCE_TOOL_COMPATIBILITY"
        if record.get("status") in {"TIMEOUT", "UNAVAILABLE"}:
            return f"PENDING_{record.get('status')}"
        return "FAIL_UNEXPECTED_REFERENCE_TOOL_ERROR"

    return {
        "scope": "RAW_LOCKED_XSTOP_NOT_A_BEHAVIORAL_GATE",
        "verilator": {**verilator, "classification": classify("verilator", verilator)},
        "yosys": {**yosys, "classification": classify("yosys", yosys)},
        "interpretation": (
            "The immutable concatenated artifact includes a resource-file list and uses source constructs "
            "outside this Yosys frontend. These execution constraints are PENDING assembly/tool work, "
            "not a target functional failure."
        ),
    }


def direct_checks(top_module: Any, frozen_ports: list[dict[str, object]]) -> dict[str, object]:
    """Run only the diagnostics that the current top explicitly implements."""

    probe = top_module.UHSCTop()
    probe_observations: list[dict[str, int]] = []
    simulator = Simulator(probe)

    def probe_process() -> Any:
        for reset in (0, 1):
            yield probe.reset.eq(reset)
            yield Settle()
            probe_observations.append({
                "reset": reset,
                "closure_missing": (yield probe.closure_missing),
                "closure_missing_count": (yield probe.closure_missing_count),
                "closure_complete": (yield probe.closure_complete),
                "cpu_halted": (yield probe.cpu_halted),
                "mem_d_ready": (yield probe.mem_d_ready),
            })

    simulator.add_process(probe_process)
    simulator.run()
    expected_probe = {
        "closure_missing": 1,
        "closure_missing_count": 4,
        "closure_complete": 0,
        "cpu_halted": 1,
        "mem_d_ready": 0,
    }
    probe_pass = all(all(row[name] == expected for name, expected in expected_probe.items()) for row in probe_observations)

    envelope = top_module.UHSCTop(injected_dependencies={"full_port_specs": frozen_ports})
    input_names = [str(port["name"]) for port in frozen_ports if port["direction"] == "input"]
    output_names = [str(port["name"]) for port in frozen_ports if port["direction"] == "output"]
    output_nonzero: list[dict[str, object]] = []
    envelope_sim = Simulator(envelope)

    def envelope_process() -> Any:
        for vector in (0, 1):
            for name in input_names:
                signal = envelope.full_inventory[name]
                value = 0 if vector == 0 else (1 << len(signal)) - 1
                yield signal.eq(value)
            yield Settle()
            for name in output_names:
                signal = envelope.full_inventory[name]
                observed = (yield signal)
                if observed != 0:
                    output_nonzero.append({"vector": vector, "name": name, "value": observed})

    envelope_sim.add_process(envelope_process)
    envelope_sim.run()
    envelope_pass = not output_nonzero
    return {
        "status": "PASS_BOUNDED_DIAGNOSTIC_QUIESCENT_ENVELOPE" if probe_pass and envelope_pass else "FAIL",
        "diagnostic_probe": {
            "vectors": len(probe_observations),
            "observations": probe_observations,
            "expected": expected_probe,
            "status": "PASS" if probe_pass else "FAIL",
        },
        "full_envelope_quiescence": {
            "vectors": 2,
            "driven_inputs": len(input_names),
            "observed_outputs": len(output_names),
            "nonzero_outputs": output_nonzero,
            "status": "PASS" if envelope_pass else "FAIL",
            "meaning": "Current local envelope tie-off behavior only; not locked-XSTop behavioral equivalence.",
        },
    }


def tool_gate_status(tools: Mapping[str, Mapping[str, object]]) -> str:
    return "PASS" if all(record.get("status") == "PASS" for record in tools.values()) else "FAIL"


def current_metrics() -> dict[str, object]:
    if not NORMALIZED_METRICS.is_file():
        return {"status": "PENDING_MISSING_NORMALIZED_METRICS"}
    payload = read_json(NORMALIZED_METRICS)
    return {
        "source": str(NORMALIZED_METRICS.relative_to(ROOT)).replace("\\", "/"),
        "port_envelope_coverage": payload.get("port_envelope_coverage", {}),
        "family_closure_coverage": payload.get("family_closure_coverage", {}),
        "leaf_behavioral_coverage": payload.get("leaf_behavioral_coverage", {}),
        "full_top_behavior": payload.get("full_top_behavior"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xstop", type=Path, default=DEFAULT_XSTOP, help="immutable locked XSTop.sv access path")
    parser.add_argument("--skip-raw-reference-tools", action="store_true", help="skip the non-standalone raw XSTop tool probe")
    args = parser.parse_args()

    reference_path = args.xstop
    if not reference_path.is_file():
        raise FileNotFoundError(reference_path)
    inventory = read_json(INVENTORY)
    frozen_ports = [normalize_port(item) for item in inventory.get("ports", []) if isinstance(item, Mapping)]
    header = capture_xstop_header(reference_path)
    parsed_ports = parse_ansi_header(header)
    reference_sha = digest_file(reference_path)
    reference_integrity = {
        "canonical_path": WSL_XSTOP,
        "local_access_path": str(reference_path),
        "bytes": reference_path.stat().st_size,
        "sha256": reference_sha,
        "expected_bytes": EXPECTED_XSTOP_BYTES,
        "expected_sha256": EXPECTED_XSTOP_SHA256,
        "source_commit": inventory.get("source_commit"),
        "expected_source_commit": EXPECTED_SOURCE_COMMIT,
        "status": "PASS" if reference_path.stat().st_size == EXPECTED_XSTOP_BYTES
        and reference_sha == EXPECTED_XSTOP_SHA256
        and inventory.get("source_commit") == EXPECTED_SOURCE_COMMIT else "FAIL",
    }
    inventory_header = {
        "header_sha256": hashlib.sha256(header).hexdigest(),
        "expected_header_sha256": inventory.get("header_sha256"),
        "parsed_port_count": len(parsed_ports),
        "frozen_port_count": len(frozen_ports),
        "comparison": schema_comparison(parsed_ports, frozen_ports),
    }
    inventory_header["status"] = "PASS" if inventory_header["header_sha256"] == inventory_header["expected_header_sha256"] \
        and inventory_header["comparison"]["status"] == "PASS" else "FAIL"

    top_module = load_build(TOP_BUILD, "v2_full_top_uhsc")
    roots_module = load_build(ROOT_BUILD, "v2_full_top_source_root")
    WORK.mkdir(parents=True, exist_ok=True)
    uhsc_name = "UHSCTopFullTopContract"
    source_name = "UHSCXSTopFullTopContract"
    reference_name = "LockedXSTopPortContract"
    uhsc_rtl = top_module.build_verilog({"module": uhsc_name}, {"full_port_specs": frozen_ports})
    source_rtl = roots_module.build_verilog(
        {"root": "XSTop", "module": source_name}, {"full_port_specs": frozen_ports}
    )
    reference_rtl = render_reference_carrier(reference_name, parsed_ports)
    uhsc_path = WORK / "UHSCTopFullTopContract.sv"
    source_path = WORK / "UHSCXSTopFullTopContract.sv"
    reference_contract_path = WORK / "LockedXSTopPortContract.sv"
    artifacts = {
        "uhsc_top": write_text(uhsc_path, uhsc_rtl),
        "source_named_xstop": write_text(source_path, source_rtl),
        "locked_header_contract_carrier": write_text(reference_contract_path, reference_rtl),
    }
    uhsc_ports = parse_generated_ports(uhsc_rtl, uhsc_name)
    source_ports = parse_generated_ports(source_rtl, source_name)
    reference_match = re.search(rf"(?s)^module\s+{reference_name}\s*\(.*?\);", reference_rtl)
    if reference_match is None:
        raise ValueError(f"missing reference module header: {reference_name}")
    reference_contract_ports = parse_ansi_header(reference_match.group(0).encode("utf-8"))
    envelopes = {
        "UHSCTop": {
            "port_contract": schema_comparison(parsed_ports, uhsc_ports),
            "handshake_contract": handshake_contract(parsed_ports, uhsc_ports),
            "tools": run_tools(uhsc_path, uhsc_name),
        },
        "source_named_XSTop": {
            "port_contract": schema_comparison(parsed_ports, source_ports),
            "handshake_contract": handshake_contract(parsed_ports, source_ports),
            "tools": run_tools(source_path, source_name),
        },
        "locked_header_contract_carrier": {
            "port_contract": schema_comparison(parsed_ports, reference_contract_ports),
            "handshake_contract": handshake_contract(parsed_ports, reference_contract_ports),
            "tools": run_tools(reference_contract_path, reference_name),
            "scope": "REFERENCE_PORT_CONTRACT_ONLY_NOT_XSTOP_BEHAVIOR",
        },
    }
    for item in envelopes.values():
        item["status"] = "PASS" if item["port_contract"]["status"] == "PASS" \
            and item["handshake_contract"]["status"] == "PASS" \
            and tool_gate_status(item["tools"]) == "PASS" else "FAIL"

    direct = direct_checks(top_module, frozen_ports)
    raw_reference = {"status": "SKIPPED"} if args.skip_raw_reference_tools else raw_reference_tool_probe()
    unexpected_raw_failure = any(
        record.get("classification") == "FAIL_UNEXPECTED_REFERENCE_TOOL_ERROR"
        for record in raw_reference.values() if isinstance(record, dict)
    )
    direct_status = str(direct["status"])
    structural_pass = reference_integrity["status"] == "PASS" and inventory_header["status"] == "PASS" \
        and direct_status.startswith("PASS") and all(item["status"] == "PASS" for item in envelopes.values())
    status = "PASS_BOUNDED_FULL_TOP_PORT_CONTRACT_PENDING_BEHAVIOR" if structural_pass and not unexpected_raw_failure \
        else "FAIL_FULL_TOP_CONTRACT"
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FULL_TOP_CONTRACT_COMPARISON",
        "batch_id": "V2-FULL-XSTOP-BEHAVIORAL-DIFFERENTIAL-PRECONDITION",
        "status": status,
        "reference_integrity": reference_integrity,
        "locked_header_inventory": inventory_header,
        "normalized_top_metrics": current_metrics(),
        "artifacts": artifacts,
        "envelopes": envelopes,
        "direct": direct,
        "raw_locked_reference_tool_probe": raw_reference,
        "flat_module_name_comparison": {
            "status": "NON_COMPARABLE_NOT_A_FUNCTIONAL_GATE",
            "reason": (
                "Locked Chisel output uses flattened generated module names while local Amaranth output uses "
                "hierarchical names. No instance-normalization map exists, so this count cannot be a functional FAIL."
            ),
            "behavioral_gate": False,
        },
        "gates": {
            "LOCKED_REFERENCE_INTEGRITY": reference_integrity["status"],
            "LOCKED_HEADER_TO_FROZEN_INVENTORY": inventory_header["status"],
            "UHSC_TOP_PORT_DIRECTION_WIDTH": envelopes["UHSCTop"]["port_contract"]["status"],
            "UHSC_TOP_VALID_READY_DIRECTION": envelopes["UHSCTop"]["handshake_contract"]["status"],
            "SOURCE_NAMED_XSTOP_PORT_DIRECTION_WIDTH": envelopes["source_named_XSTop"]["port_contract"]["status"],
            "SOURCE_NAMED_XSTOP_VALID_READY_DIRECTION": envelopes["source_named_XSTop"]["handshake_contract"]["status"],
            "DIRECT_TEST_PASS_BOUNDED": direct["status"],
            "REFERENCE_PORT_CONTRACT": envelopes["locked_header_contract_carrier"]["status"],
            "VERILATOR": "PASS" if all(item["tools"]["verilator"]["status"] == "PASS" for item in envelopes.values()) else "FAIL",
            "YOSYS": "PASS" if all(item["tools"]["yosys"]["status"] == "PASS" for item in envelopes.values()) else "FAIL",
            "FULL_TOP_BEHAVIORAL_DIFFERENTIAL": "PENDING_FULL_CHILD_BEHAVIORAL_DIFFERENTIAL",
            "FLAT_MODULE_NAMES": "NON_COMPARABLE_NOT_A_FUNCTIONAL_GATE",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "pending": [
            "UHSCTop direct checks exercise only its explicit diagnostic/quiescent envelope; all full-envelope outputs are current tie-offs.",
            "XSCore, L2Top, XSTile, Frontend, Backend, MemBlock, HuanCun, and external Diplomacy closures are not a behaviorally connected full XSTop.",
            "The locked XSTop artifact is not currently assembled as a standalone reference DUT: Verilator reaches its appended resource-file list and this Yosys frontend rejects an upstream construct.",
            "No executable full-top target/reference transaction differential exists; child/parent bounded passes cannot be promoted to full-top behavior.",
            "License review and explicit user acceptance remain pending.",
        ],
        "acceptance_eligible": False,
        "accepted": False,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "status": payload["status"],
        "uhsc_ports": envelopes["UHSCTop"]["port_contract"]["candidate_port_count"],
        "xstop_ports": envelopes["source_named_XSTop"]["port_contract"]["candidate_port_count"],
        "handshake_channels": envelopes["UHSCTop"]["handshake_contract"]["checked_channels"],
        "direct": direct["status"],
        "verilator": payload["gates"]["VERILATOR"],
        "yosys": payload["gates"]["YOSYS"],
        "behavior": payload["gates"]["FULL_TOP_BEHAVIORAL_DIFFERENTIAL"],
        "accepted": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0 if status.startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
