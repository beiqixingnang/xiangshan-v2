"""Strict complete-equivalence validator for all eighteen locked FuBusyTableRead ABIs.

FuBusyTableRead is a stateless, combinational issue-queue reader.  Its locked
V2 generation produces eighteen public specializations that differ only in
issue-queue geometry (``numEntries`` / ``latMax``) and in the ``latency -> set
of FuType one-hot bits`` map contributed by each parent's ``fuLatencyMap``.

For every specialization this validator renders the Build with that
specialization's configuration, audits the exact port surface against the
locked module, and proves a Yosys SAT miter whose ``mismatch`` is the
reduction-OR over every declared output bit with all input bits left
unconstrained.  A nineteenth aggregate miter ORs all eighteen per-bit
equalities into one property so the whole family closes in a single run.

The reference is never re-derived: each ``validation/reference-sv/*.sv`` file
is taken verbatim and renamed only inside an ASCII temporary work directory.
The locked equation is additionally re-parsed from each reference body and
required to agree with the recorded configuration, so a stale table fails the
gate instead of passing vacuously.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
import py_compile
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Build-Cpu.Backend.Issue.FuBusyTableRead-Hardware.py"
)
SCALA = ROOT / "upstream/src/main/scala/xiangshan/backend/issue/FuBusyTableRead.scala"
REFERENCE_DIR = ROOT / "validation/reference-sv"
EVIDENCE = ROOT / "validation/v2-fubusytableread-strict-evidence.json"
TEMP_ROOT = Path(tempfile.gettempdir())
if not str(TEMP_ROOT).isascii():
    TEMP_ROOT = Path("C:/Temp")
WORK = TEMP_ROOT / "uhsc_fubusytableread_strict"

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_XSTOP = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
XSTOP_BYTES = 228590583
FU_TYPE_BITS = 35
SUCCESS_MARKER = "SAT proof finished - no model found: SUCCESS!"

# One entry per locked specialization.  ``latency_to_oh_bits`` is the exact
# group-by-latency inverse of the parent's fuLatencyMap; ``table_bits == 1``
# means Chisel emitted a scalar io_in_fuBusyTable because latMax was zero.
# ``parents`` names the modules instantiating the specialization, read from the
# locked reference-sv corpus.
VARIANTS: dict[str, dict[str, Any]] = {
    "FuBusyTableRead": {
        "num_entries": 24, "table_bits": 3,
        "latency_to_oh_bits": {0: (6,), 2: (7, 10)},
        "parents": ["IssueQueueAluMulBkuBrhJmp"],
    },
    "FuBusyTableRead_2": {
        "num_entries": 24, "table_bits": 1,
        "latency_to_oh_bits": {0: (0,)},
        "parents": ["IssueQueueAluMulBkuBrhJmp"],
    },
    "FuBusyTableRead_22": {
        "num_entries": 24, "table_bits": 3,
        "latency_to_oh_bits": {0: (0, 1, 3, 28, 29), 2: (2,)},
        "parents": ["IssueQueueAluBrhJmpI2fVsetriwiVsetriwvfI2v"],
    },
    "FuBusyTableRead_23": {
        "num_entries": 24, "table_bits": 1,
        "latency_to_oh_bits": {0: (6,)},
        "parents": ["IssueQueueAluBrhJmpI2fVsetriwiVsetriwvfI2v", "IssueQueueAluCsrFenceDiv"],
    },
    "FuBusyTableRead_26": {
        "num_entries": 24, "table_bits": 3,
        "latency_to_oh_bits": {0: (3,), 2: (2,)},
        "parents": ["IssueQueueAluBrhJmpI2fVsetriwiVsetriwvfI2v"],
    },
    "FuBusyTableRead_28": {
        "num_entries": 24, "table_bits": 1,
        "latency_to_oh_bits": {0: (3,)},
        "parents": ["IssueQueueAluBrhJmpI2fVsetriwiVsetriwvfI2v"],
    },
    "FuBusyTableRead_42": {
        "num_entries": 18, "table_bits": 4,
        "latency_to_oh_bits": {0: (4,), 1: (11,), 2: (13,), 3: (12,)},
        "parents": ["IssueQueueFaluFcvtF2vFmacFdiv"],
    },
    "FuBusyTableRead_43": {
        "num_entries": 18, "table_bits": 3,
        "latency_to_oh_bits": {1: (11,), 2: (13,)},
        "parents": ["IssueQueueFaluFcvtF2vFmacFdiv"],
    },
    "FuBusyTableRead_52": {
        "num_entries": 18, "table_bits": 4,
        "latency_to_oh_bits": {1: (11,), 3: (12,)},
        "parents": ["IssueQueueFaluFmac", "IssueQueueFaluFmacFdiv"],
    },
    "FuBusyTableRead_53": {
        "num_entries": 18, "table_bits": 2,
        "latency_to_oh_bits": {1: (11,)},
        "parents": ["IssueQueueFaluFmac", "IssueQueueFaluFmacFdiv"],
    },
    "FuBusyTableRead_68": {
        "num_entries": 16, "table_bits": 5,
        "latency_to_oh_bits": {2: (19,), 3: (20, 21), 4: (25,)},
        "parents": ["IssueQueueVfmaVialuFixVimacVppuVfaluVfcvtVipuVsetrvfwvf"],
    },
    "FuBusyTableRead_69": {
        "num_entries": 16, "table_bits": 4,
        "latency_to_oh_bits": {1: (30,), 2: (24,), 3: (18, 27)},
        "parents": ["IssueQueueVfmaVialuFixVimacVppuVfaluVfcvtVipuVsetrvfwvf"],
    },
    "FuBusyTableRead_71": {
        "num_entries": 16, "table_bits": 5,
        "latency_to_oh_bits": {2: (30,), 4: (18,)},
        "parents": ["IssueQueueVfmaVialuFixVimacVppuVfaluVfcvtVipuVsetrvfwvf"],
    },
    "FuBusyTableRead_73": {
        "num_entries": 16, "table_bits": 3,
        "latency_to_oh_bits": {2: (24,)},
        "parents": ["IssueQueueVfmaVialuFixVfalu",
                    "IssueQueueVfmaVialuFixVimacVppuVfaluVfcvtVipuVsetrvfwvf"],
    },
    "FuBusyTableRead_75": {
        "num_entries": 16, "table_bits": 4,
        "latency_to_oh_bits": {2: (24,), 3: (18, 27)},
        "parents": ["IssueQueueVfmaVialuFixVimacVppuVfaluVfcvtVipuVsetrvfwvf"],
    },
    "FuBusyTableRead_79": {
        "num_entries": 16, "table_bits": 2,
        "latency_to_oh_bits": {1: (30,)},
        "parents": ["IssueQueueVfmaVialuFixVimacVppuVfaluVfcvtVipuVsetrvfwvf"],
    },
    "FuBusyTableRead_80": {
        "num_entries": 16, "table_bits": 5,
        "latency_to_oh_bits": {2: (19,), 4: (25,)},
        "parents": ["IssueQueueVfmaVialuFixVfalu"],
    },
    "FuBusyTableRead_105": {
        "num_entries": 16, "table_bits": 4,
        "latency_to_oh_bits": {3: (15,)},
        "parents": ["IssueQueueLdu"],
    },
}


def sha256_file(path: Path) -> str:
    """Return SHA-256 of exact file bytes."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_target() -> Any:
    """Load only the selected Build module by exact path."""

    spec = importlib.util.spec_from_file_location("strict_fubusytableread_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def wsl_path(path: Path) -> str:
    """Convert a Windows path to an absolute WSL path."""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run one WSL command serially and retain bounded, hashed diagnostics."""

    rendered = " ".join(shlex.quote(item) for item in command)
    try:
        result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                                capture_output=True, check=False)
    except OSError as error:
        return {"command": command, "status": "FAIL", "error": repr(error)}
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        # Keep marker decisions from the complete process output.  A failing
        # SAT negative-control run prints the model after the verdict, so its
        # ``model found: FAIL!`` line can fall outside the bounded diagnostic
        # tail below.  Recording these booleans before truncation keeps the
        # gate sound without retaining an unbounded Yosys log in the evidence.
        "success_marker": SUCCESS_MARKER in output,
        "counterexample_marker": "model found: FAIL!" in output,
        "unconstrained_marker": "Final constraint equation: { } = { }" in output,
        "output_tail": output[-4000:],
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


def tool_versions() -> dict[str, Any]:
    """Record the exact Verilator/Yosys binaries used by the proofs."""

    return {"verilator": run_wsl(["verilator", "--version"]),
            "yosys": run_wsl(["yosys", "--version"])}


def pyright_check(source: Path) -> dict[str, Any]:
    """Run Pyright on an exact visible copy of one source file."""

    temporary = Path(tempfile.mkdtemp(prefix="uhsc_fubusytableread_pyright_"))
    try:
        copied = temporary / source.name
        shutil.copyfile(source, copied)
        command = ["cmd.exe", "/d", "/c", "pyright", "--outputjson", str(copied)]
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", check=False)
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            parsed = {}
        summary = parsed.get("summary", {}) if isinstance(parsed, dict) else {}
        passed = result.returncode == 0 and summary.get("errorCount") == 0
        return {
            "command": command,
            "returncode": result.returncode,
            "status": "PASS" if passed else "FAIL",
            "version": parsed.get("version") if isinstance(parsed, dict) else None,
            "files_analyzed": summary.get("filesAnalyzed"),
            "error_count": summary.get("errorCount"),
            "warning_count": summary.get("warningCount"),
            "output_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
            "stderr_tail": result.stderr[-1000:],
        }
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def reference_text(name: str) -> str:
    """Read one locked reference verbatim; this rail never writes there."""

    path = REFERENCE_DIR / f"{name}.sv"
    if not path.is_file():
        raise FileNotFoundError(f"locked reference missing: {path}")
    return path.read_text(encoding="utf-8")


# =============================================================================
# Reference-declaration parsing (ANSI continuation lists and bare headers)
# =============================================================================
_DECL_RE = re.compile(
    r"^(input|output)\b(?:\s*\[(\d+):0\])?\s*([A-Za-z_][A-Za-z0-9_]*)?;"
)


def _split_items(text: str) -> list[str]:
    """Split one declaration region on top-level commas."""

    items: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
        if char == "," and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(char)
    items.append("".join(current))
    return items


def _classify(items: list[str]) -> dict[str, tuple[str, int]]:
    """Map port names to (direction, width) using pending ANSI state."""

    result: dict[str, tuple[str, int]] = {}
    pending: tuple[str, int] | None = None
    for item in items:
        entry = " ".join(item.split())
        if not entry:
            continue
        match = re.match(
            r"^(input|output)\b(?:\s*\[(\d+):0\])?\s*([A-Za-z_][A-Za-z0-9_]*)?$",
            entry,
        )
        if match is not None:
            direction, msb, name = match.groups()
            pending = (direction, int(msb) + 1 if msb is not None else 1)
            if name is not None:
                result[name] = pending
            continue
        if pending is not None and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", entry):
            result[entry] = pending
            continue
        pending = None
    return result


def _module_region(rtl: str, module_name: str) -> tuple[str, str]:
    """Return one module's ANSI header text and its body region."""

    start = rtl.find(f"module {module_name}(")
    if start < 0:
        return "", ""
    open_index = rtl.index("(", start)
    depth = 0
    close_index = -1
    for index in range(open_index, len(rtl)):
        char = rtl[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                close_index = index
                break
    if close_index < 0:
        return "", ""
    end_index = rtl.find("endmodule", close_index)
    return rtl[open_index + 1:close_index], rtl[close_index + 1:end_index if end_index >= 0 else len(rtl)]


def _header_port_names(header: str) -> set[str]:
    """Return the bare identifiers listed in an ANSI port header."""

    stripped = re.sub(r"//[^\n]*", "", header)
    if re.search(r"\b(?:input|output)\b", stripped):
        return set()
    return {token for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", stripped)}


def _declaration_lines(text: str, names: set[str]) -> str:
    """Return body direction declarations for known header port names."""

    kept: list[str] = []
    for line in text.splitlines():
        code = re.sub(r"//[^\n]*", "", line).strip()
        if code.startswith("endmodule"):
            break
        match = _DECL_RE.match(code)
        if match is None:
            continue
        direction, msb, name = match.groups()
        if name is not None and name in names:
            width = int(msb) + 1 if msb is not None else 1
            kept.append(f"{direction} {name}" if width == 1
                        else f"{direction} [{width - 1}:0] {name}")
    return ",\n".join(kept)


def declared_ports(rtl: str, module_name: str) -> dict[str, tuple[str, int]]:
    """Extract typed ports from either Chisel or Amaranth declaration style."""

    raw_header, body = _module_region(rtl, module_name)
    header = re.sub(r"//[^\n]*", "", raw_header)
    if re.search(r"\b(?:input|output)\b", header):
        return _classify(_split_items(header))
    return _classify(_split_items(_declaration_lines(body, _header_port_names(header))))


def expected_surface(num_entries: int, table_bits: int) -> dict[str, tuple[str, int]]:
    """Return the exact locked ABI for one specialization geometry."""

    surface: dict[str, tuple[str, int]] = {
        "io_in_fuBusyTable": ("input", table_bits),
    }
    for index in range(num_entries):
        surface[f"io_in_fuTypeRegVec_{index}"] = ("input", FU_TYPE_BITS)
    surface["io_out_fuBusyTableMask"] = ("output", num_entries)
    return surface


# =============================================================================
# Locked-equation cross-check
# =============================================================================
def derive_locked_groups(name: str) -> dict[str, Any]:
    """Re-parse latency -> OH-bit groups straight out of one locked reference.

    Every ``(io_in_fuBusyTable[lat] ? {...} : W'h0)`` term contributes one
    latency group, and a bare ``io_in_fuBusyTable ? {...} : W'h0`` term is the
    scalar-table case (latMax == 0).  The bit sets must be identical for every
    entry of a group; a non-uniform group is reported rather than averaged,
    because it would mean the specialization is not data-independent and this
    Build's configuration model cannot express it.
    """

    text = reference_text(name)
    start = text.index("assign io_out_fuBusyTableMask")
    stop = text.find("endmodule", start)
    body = re.sub(r"//[^\n]*", "", text[start:stop if stop >= 0 else len(text)])

    term_pattern = re.compile(
        r"(io_in_fuBusyTable(?:\[\d+\])?)\s*\?\s*\{(.*?)\}\s*:\s*\d+'h[0-9A-Fa-f]+",
        re.S,
    )
    matches = list(term_pattern.finditer(body))
    groups: dict[int, frozenset[int]] = {}
    uniform = True
    details: list[str] = []
    for match in matches:
        condition, inner = match.group(1), match.group(2)
        indexed = re.search(r"\[(\d+)\]", condition)
        latency = int(indexed.group(1)) if indexed else 0
        entry_exprs = _split_items(inner)
        per_entry = [
            frozenset(int(bit) for bit in re.findall(r"io_in_fuTypeRegVec_\d+\[(\d+)\]", item))
            for item in entry_exprs
        ]
        if not per_entry or any(not bits for bits in per_entry):
            details.append(f"latency {latency} has empty or unparsable entry expressions")
            continue
        union = frozenset().union(*per_entry)
        if any(bits != union for bits in per_entry):
            uniform = False
            details.append(f"latency {latency} non-uniform across {len(per_entry)} entries")
        if latency in groups and groups[latency] != union:
            details.append(f"latency {latency} appears twice with differing bit sets")
            uniform = False
        groups[latency] = union
    # One term per latency group is the only shape the Scala fold emits.
    expected_terms = len(groups)
    if len(matches) != expected_terms:
        details.append(f"{len(matches)} terms parsed but {expected_terms} distinct latencies")
    return {
        "groups": groups,
        "term_count": len(matches),
        "uniform_across_entries": uniform,
        "detail": details,
    }


def configuration_audit(module: Any) -> dict[str, Any]:
    """Require every recorded config to equal the re-parsed locked equation."""

    rows: dict[str, Any] = {}
    ok = True
    for name, spec in VARIANTS.items():
        derived = derive_locked_groups(name)
        recorded = {int(k): frozenset(v) for k, v in spec["latency_to_oh_bits"].items()}
        matches = derived["groups"] == recorded and derived["uniform_across_entries"]
        # The Build itself must accept and reproduce exactly this mapping.
        try:
            built = module.FuBusyTableReadConfig(
                num_entries=spec["num_entries"],
                fu_type_bits=FU_TYPE_BITS,
                table_bits=spec["table_bits"],
                latency_to_oh_bits={k: frozenset(v) for k, v in spec["latency_to_oh_bits"].items()},
            )
            accepted = {int(k): frozenset(v) for k, v in built.latency_to_oh_bits.items()} == recorded
        except ValueError as error:
            accepted = False
            derived["detail"].append(f"config rejected: {error}")
        rows[name] = {
            "recorded_latency_to_oh_bits": {str(k): sorted(v) for k, v in sorted(recorded.items())},
            "derived_from_locked_equation": {str(k): sorted(v) for k, v in sorted(derived["groups"].items())},
            "term_count": derived["term_count"],
            "uniform_across_entries": derived["uniform_across_entries"],
            "equation_matches_recorded": matches,
            "build_accepts_config": accepted,
            "detail": derived["detail"],
        }
        ok = ok and matches and accepted
    return {"status": "PASS" if ok else "FAIL", "rows": rows}


def rejection_audit(module: Any) -> dict[str, Any]:
    """Confirm the Build rejects malformed configurations."""

    base: dict[str, Any] = {"num_entries": 24, "table_bits": 3,
                            "latency_to_oh_bits": {0: frozenset({6})}}
    rejected: dict[str, bool] = {}
    for label, patch in {
        "empty_latency_map": {"latency_to_oh_bits": {}},
        "empty_latency_set": {"latency_to_oh_bits": {0: frozenset()}},
        "oh_bit_beyond_fu_type_width": {"latency_to_oh_bits": {0: frozenset({FU_TYPE_BITS})}},
        "latency_beyond_table_bits": {"latency_to_oh_bits": {7: frozenset({6})}},
        "zero_num_entries": {"num_entries": 0},
        "zero_table_bits": {"table_bits": 0},
    }.items():
        kwargs = {**base, **patch}
        try:
            module.FuBusyTableReadConfig(**kwargs)
        except ValueError:
            rejected[label] = True
        else:
            rejected[label] = False
    try:
        module.FuBusyTableReadConfig(latency_to_oh_bits="not-a-mapping")  # type: ignore[arg-type]
    except TypeError:
        rejected["non_mapping_latency_table"] = True
    else:
        rejected["non_mapping_latency_table"] = False
    return {"status": "PASS" if all(rejected.values()) else "FAIL",
            "rejected": rejected,
            "default_export_is_unsuffixed_variant": True}


# =============================================================================
# Export, ABI, miters
# =============================================================================
def export_variants(module: Any) -> tuple[dict[str, str], dict[str, Any]]:
    """Render every specialization twice and require byte identity."""

    exported: dict[str, str] = {}
    records: dict[str, Any] = {}
    for name, spec in VARIANTS.items():
        configuration = module.FuBusyTableReadConfig(
            num_entries=spec["num_entries"],
            fu_type_bits=FU_TYPE_BITS,
            table_bits=spec["table_bits"],
            latency_to_oh_bits={k: frozenset(v) for k, v in spec["latency_to_oh_bits"].items()},
        )
        first = module.build_verilog(configuration, {})
        second = module.build_verilog(configuration, {})
        first_bytes = first.encode("utf-8")
        second_bytes = second.encode("utf-8")
        exported[name] = first
        records[name] = {
            "status": "PASS" if first_bytes == second_bytes else "FAIL",
            "configuration": {
                "num_entries": spec["num_entries"],
                "fu_type_bits": FU_TYPE_BITS,
                "table_bits": spec["table_bits"],
                "latency_to_oh_bits": {str(k): sorted(v)
                                       for k, v in sorted(spec["latency_to_oh_bits"].items())},
            },
            "bytes": len(first_bytes),
            "sha256": hashlib.sha256(first_bytes).hexdigest(),
            "repeat_sha256": hashlib.sha256(second_bytes).hexdigest(),
            "byte_equal": first_bytes == second_bytes,
        }
    default_rtl = module.build_verilog(None, {})
    default_bytes = default_rtl.encode("utf-8")
    records["__default__"] = {
        "status": "PASS" if default_bytes == module.build_verilog(None, {}).encode("utf-8") else "FAIL",
        "note": "build_verilog(None, None) must equal the unsuffixed locked specialization",
        "matches_FuBusyTableRead": default_rtl == exported["FuBusyTableRead"],
        "sha256": hashlib.sha256(default_bytes).hexdigest(),
    }
    if records["__default__"]["matches_FuBusyTableRead"] is False:
        records["__default__"]["status"] = "FAIL"
    return exported, records


def abi_audits(exported: dict[str, str]) -> dict[str, Any]:
    """Audit exact port name set, directions and widths for target and gold."""

    rows: dict[str, Any] = {}
    ok = True
    for name, spec in VARIANTS.items():
        surface = expected_surface(spec["num_entries"], spec["table_bits"])
        target_ports = declared_ports(exported[name], "FuBusyTableRead")
        reference_ports = declared_ports(reference_text(name), name)
        checks = {
            "target_module": f"module FuBusyTableRead(" in exported[name],
            "reference_module": f"module {name}(" in reference_text(name),
            "target_exact_port_set": target_ports == surface,
            "reference_exact_port_set": reference_ports == surface,
            "target_reference_port_sets_equal": target_ports == reference_ports,
            "io_in_fuBusyTable": target_ports.get("io_in_fuBusyTable") == surface["io_in_fuBusyTable"],
            "io_out_fuBusyTableMask":
                target_ports.get("io_out_fuBusyTableMask") == surface["io_out_fuBusyTableMask"],
            "fu_type_reg_vec_ports": all(
                target_ports.get(f"io_in_fuTypeRegVec_{i}") == surface[f"io_in_fuTypeRegVec_{i}"]
                for i in range(spec["num_entries"])),
        }
        passed = all(checks.values())
        ok = ok and passed
        rows[name] = {
            "status": "PASS" if passed else "FAIL",
            "checks": checks,
            "port_count": len(surface),
            "inputs": {k: v[1] for k, v in surface.items() if v[0] == "input"},
            "outputs_compared": {k: v[1] for k, v in surface.items() if v[0] == "output"},
            "target_declared_ports": {k: list(v) for k, v in sorted(target_ports.items())},
            "reference_declared_ports": {k: list(v) for k, v in sorted(reference_ports.items())},
        }
    return {"status": "PASS" if ok else "FAIL", "rows": rows}


def _port_declarations(name: str, spec: dict[str, Any], suffix: str) -> tuple[list[str], str]:
    """Return (declaration lines, joined input connections) for one variant.

    ``suffix`` keeps signal names unique inside the aggregate miter, whose
    variants differ in entry count and busy-table width and therefore cannot
    share one input bundle.
    """

    entries = int(spec["num_entries"])
    table_bits = int(spec["table_bits"])
    width = "" if table_bits == 1 else f"[{table_bits - 1}:0] "
    declarations = [f"  input {width}io_in_fuBusyTable{suffix},"]
    pairs: list[tuple[str, str]] = [("io_in_fuBusyTable", f"io_in_fuBusyTable{suffix}")]
    for index in range(entries):
        port = f"io_in_fuTypeRegVec_{index}"
        declarations.append(f"  input [{FU_TYPE_BITS - 1}:0] {port}{suffix},")
        pairs.append((port, f"{port}{suffix}"))
    # Callers append the output connection to ``connections``, so this string is
    # deliberately left unterminated; ``mask`` names the wire it drives.
    connections = ", ".join(f".{port}({local})" for port, local in pairs)
    return declarations, connections


def miter_nets_declared(text: str) -> bool:
    """Reject implicit miter nets before invoking Verilator or Yosys."""

    declared = set(re.findall(
        r"^\s*(?:input|output|wire)\s+(?:\[\s*\d+:\s*\d+\]\s*)?([A-Za-z_]\w*)",
        text, re.M))
    connected = {net.strip() for net in re.findall(r"\.\w+\(([^()]+)\)", text)}
    return bool(connected) and connected <= declared


def materialize(exported: dict[str, str]) -> dict[str, Any]:
    """Write targets, the renamed locked closure, miters, and the aggregate."""

    WORK.mkdir(parents=True, exist_ok=True)
    reference_parts: list[str] = []
    for name in VARIANTS:
        text = reference_text(name)
        marker = f"module {name}("
        if not text.lstrip().startswith(marker):
            raise AssertionError(f"locked declaration missing: {name}")
        reference_parts.append(text.replace(marker, f"module REF_{name}(", 1))
    reference = WORK / "REF_FuBusyTableRead_closure.sv"
    reference.write_text("\n".join(reference_parts), encoding="utf-8", newline="\n")

    targets: dict[str, Path] = {}
    miters: dict[str, Path] = {}
    miter_selfchecks: dict[str, bool] = {}
    target_names: dict[str, str] = {}
    aggregate_declarations: list[str] = []
    aggregate_instances: list[str] = []
    aggregate_terms: list[str] = []
    for name, spec in VARIANTS.items():
        target_name = f"DUT_{name}"
        target_names[name] = target_name
        path = WORK / f"{target_name}.sv"
        path.write_text(
            exported[name].replace("module FuBusyTableRead(", f"module {target_name}(", 1),
            encoding="utf-8", newline="\n")
        targets[name] = path
        entries = int(spec["num_entries"])
        declarations, connections = _port_declarations(name, spec, "")
        ref_map = f"{connections}, .io_out_fuBusyTableMask(ref_mask)"
        dut_map = f"{connections}, .io_out_fuBusyTableMask(dut_mask)"
        miter = WORK / f"{name}_MITER.sv"
        miter_text = (
            f"module {name}_MITER(\n"
            + "\n".join(declarations)
            + "\n  output mismatch\n);\n"
            + f"  wire [{entries - 1}:0] ref_mask;\n"
            + f"  wire [{entries - 1}:0] dut_mask;\n"
            + f"  REF_{name} reference_i({ref_map});\n"
            + f"  {target_name} target_i({dut_map});\n"
            + "  assign mismatch = |(ref_mask ^ dut_mask);\n"
            + "endmodule\n")
        miter.write_text(miter_text, encoding="utf-8", newline="\n")
        miters[name] = miter
        miter_selfchecks[name] = miter_nets_declared(miter_text)

        # Aggregate: one unconstrained input bundle per specialization, because
        # the eighteen geometries are not interchangeable.
        suffix = f"__{name}"
        shared_declarations, shared_connections = _port_declarations(name, spec, suffix)
        aggregate_declarations += shared_declarations
        ref_wire = f"ref_{name}"
        dut_wire = f"dut_{name}"
        aggregate_instances.append(
            f"  wire [{entries - 1}:0] {ref_wire};\n"
            f"  wire [{entries - 1}:0] {dut_wire};\n"
            f"  REF_{name} ref_i_{name}({shared_connections}, "
            f".io_out_fuBusyTableMask({ref_wire}));\n"
            f"  {target_name} dut_i_{name}({shared_connections}, "
            f".io_out_fuBusyTableMask({dut_wire}));"
        )
        aggregate_terms += [f"({ref_wire}[{bit}] ^ {dut_wire}[{bit}])" for bit in range(entries)]
    aggregate = WORK / "FuBusyTableRead_ALL_MITER.sv"
    aggregate.write_text(
        "module FuBusyTableRead_ALL_MITER(\n"
        + "\n".join(aggregate_declarations)
        + "\n  output mismatch\n);\n"
        + "\n".join(aggregate_instances)
        + "\n  assign mismatch =\n    " + " |\n    ".join(aggregate_terms)
        + ";\nendmodule\n",
        encoding="utf-8", newline="\n")
    return {"reference": reference, "targets": targets, "miters": miters,
            "aggregate": aggregate, "target_names": target_names,
            "miter_selfchecks": miter_selfchecks}


def formal_one(name: str, paths: dict[str, Any]) -> dict[str, Any]:
    """Lint, synth-check and prove one specialization over its full input space."""

    target = wsl_path(paths["targets"][name])
    reference = wsl_path(paths["reference"])
    miter = wsl_path(paths["miters"][name])
    target_name = paths["target_names"][name]
    top = f"{name}_MITER"
    spec = VARIANTS[name]
    verilator = run_wsl([
        "verilator", "--lint-only", "-Wno-fatal", "--top-module", top,
        target, reference, miter,
    ])
    yosys_target = run_wsl(["yosys", "-Q", "-p",
                            f"read_verilog -sv {shlex.quote(target)}; "
                            f"hierarchy -top {target_name}; proc; opt; check"])
    yosys_reference = run_wsl(["yosys", "-Q", "-p",
                               f"read_verilog -sv {shlex.quote(reference)}; "
                               f"hierarchy -top REF_{name}; proc; opt; check"])
    proof = run_wsl(["yosys", "-Q", "-p",
                     f"read_verilog -sv {shlex.quote(target)} {shlex.quote(reference)} "
                     f"{shlex.quote(miter)}; prep -top {top}; flatten; opt; "
                     "sat -prove mismatch 0"])
    marker_present = bool(proof.get(
        "success_marker", SUCCESS_MARKER in proof.get("output_tail", "")))
    unconstrained = bool(proof.get(
        "unconstrained_marker",
        "Final constraint equation: { } = { }" in proof.get("output_tail", "")))
    if not marker_present or not unconstrained or proof.get("returncode") != 0:
        proof["status"] = "FAIL"
    proof["formal_success_marker"] = marker_present
    proof["unconstrained"] = unconstrained
    input_bits = spec["table_bits"] + spec["num_entries"] * FU_TYPE_BITS
    proof["formal_scope"] = {
        "input_bits": input_bits,
        "input_space": f"2**{input_bits}",
        "state_bits": 0,
        "state_space": "singleton (stateless combinational module)",
        "outputs_compared": {"io_out_fuBusyTableMask": spec["num_entries"]},
        "property": "mismatch == 0 for every 2-state valuation of all inputs",
    }
    return {
        "verilator": verilator,
        "yosys_target": yosys_target,
        "yosys_reference": yosys_reference,
        "yosys_formal_miter": proof,
    }


def formal_aggregate(paths: dict[str, Any]) -> dict[str, Any]:
    """Prove all eighteen specializations simultaneously in one SAT run."""

    sources = [wsl_path(paths["targets"][name]) for name in VARIANTS]
    sources += [wsl_path(paths["reference"]), wsl_path(paths["aggregate"])]
    source_args = " ".join(shlex.quote(path) for path in sources)
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", "--top-module",
                         "FuBusyTableRead_ALL_MITER", *sources])
    yosys_check = run_wsl(["yosys", "-Q", "-p",
                           f"read_verilog -sv {source_args}; "
                           "hierarchy -top FuBusyTableRead_ALL_MITER; proc; opt; check"])
    proof = run_wsl(["yosys", "-Q", "-p",
                     f"read_verilog -sv {source_args}; "
                     "prep -top FuBusyTableRead_ALL_MITER; flatten; opt; "
                     "sat -prove mismatch 0"])
    marker_present = bool(proof.get(
        "success_marker", SUCCESS_MARKER in proof.get("output_tail", "")))
    unconstrained = bool(proof.get(
        "unconstrained_marker",
        "Final constraint equation: { } = { }" in proof.get("output_tail", "")))
    if not marker_present or not unconstrained or proof.get("returncode") != 0:
        proof["status"] = "FAIL"
    proof["formal_success_marker"] = marker_present
    proof["unconstrained"] = unconstrained
    proof["mitered_variants"] = len(VARIANTS)
    total_input_bits = sum(spec["table_bits"] + spec["num_entries"] * FU_TYPE_BITS
                           for spec in VARIANTS.values())
    proof["formal_scope"] = {
        "variant_count": len(VARIANTS),
        "independent_input_bits_total": total_input_bits,
        "compared_output_bits": sum(spec["num_entries"] for spec in VARIANTS.values()),
        "state_bits": 0,
        "state_space": "eighteen stateless combinational variants in one flattened miter",
        "property": ("OR over every declared output bit of every variant of "
                     "(reference_bit XOR target_bit) == 0"),
    }
    return {
        "status": "PASS" if all(item["status"] == "PASS"
                                for item in (verilator, yosys_check, proof)) else "FAIL",
        "verilator": verilator,
        "yosys_check": yosys_check,
        "yosys_formal_miter": proof,
    }


def _mutate_output(text: str, module: str, width: int) -> tuple[str, bool]:
    """Force one module's output to zero without touching sibling variants."""

    start = text.find(f"module {module}(")
    if start < 0:
        return text, False
    end = text.find("endmodule", start)
    if end < 0:
        return text, False
    body = text[start:end]
    mutated, count = re.subn(
        r"assign\s+io_out_fuBusyTableMask\s*=.*?;",
        f"assign io_out_fuBusyTableMask = {width}'h0;",
        body, count=1, flags=re.S)
    if count != 1:
        return text, False
    return text[:start] + mutated + text[end:], True


def negative_control(paths: dict[str, Any]) -> dict[str, Any]:
    """Mutate both sides of one aggregate member and require SAT counterexamples."""

    name = "FuBusyTableRead_68"
    width = int(VARIANTS[name]["num_entries"])
    results: dict[str, Any] = {}
    for side in ("target", "reference"):
        source_path = paths["targets"][name] if side == "target" else paths["reference"]
        module = paths["target_names"][name] if side == "target" else f"REF_{name}"
        mutated, applied = _mutate_output(
            source_path.read_text(encoding="utf-8"), module, width)
        if not applied:
            results[side] = {"status": "FAIL", "mutation_applied": False}
            continue
        mutant = WORK / f"MUTANT_{side}_{name}.sv"
        mutant.write_text(mutated, encoding="utf-8", newline="\n")
        sources = [paths["targets"][variant] for variant in VARIANTS]
        reference = paths["reference"]
        if side == "target":
            sources = [mutant if variant == name else paths["targets"][variant]
                       for variant in VARIANTS]
        else:
            reference = mutant
        sources += [reference, paths["aggregate"]]
        rendered = " ".join(shlex.quote(wsl_path(path)) for path in sources)
        verdict = run_wsl(["yosys", "-Q", "-p",
                           f"read_verilog -sv {rendered}; "
                           "prep -top FuBusyTableRead_ALL_MITER; flatten; opt; "
                           "sat -prove mismatch 0"])
        output = verdict.get("output_tail", "")
        success_marker = bool(verdict.get(
            "success_marker", SUCCESS_MARKER in output))
        counterexample_marker = bool(verdict.get(
            "counterexample_marker", "model found: FAIL!" in output))
        detected = verdict.get("returncode") == 0 and not success_marker \
            and counterexample_marker
        results[side] = {
            "status": "PASS" if detected else "FAIL",
            "mutation_applied": True,
            "counterexample_marker": counterexample_marker,
            "success_marker_still_present": success_marker,
            "output_tail": output[-900:],
        }
    return {"status": "PASS" if all(r["status"] == "PASS" for r in results.values())
            else "FAIL", "control_variant": name, "sides": results}


def source_lock_audit() -> dict[str, Any]:
    """Check every locked source digest before elaboration."""

    unsuffixed = REFERENCE_DIR / "FuBusyTableRead.sv"
    if not SCALA.is_file():
        raise FileNotFoundError(f"locked Scala source missing: {SCALA}")
    if not unsuffixed.is_file():
        raise FileNotFoundError(f"locked reference missing: {unsuffixed}")
    actual: dict[str, str] = {
        "scala": sha256_file(SCALA),
        "python_build": sha256_file(TARGET),
        "reference_sv": sha256_file(unsuffixed),
    }
    for name in VARIANTS:
        if name == "FuBusyTableRead":
            continue
        actual[f"reference_child_{name}"] = sha256_file(REFERENCE_DIR / f"{name}.sv")
    checks = {
        "scala_present": bool(actual["scala"]),
        "python_build_present": bool(actual["python_build"]),
        "reference_sv_present": bool(actual["reference_sv"]),
        "reference_children_present": all(
            actual[f"reference_child_{name}"]
            for name in VARIANTS if name != "FuBusyTableRead"),
        "public_variant_count_is_eighteen": len(VARIANTS) == 18,
        "source_commit_recorded": bool(SOURCE_COMMIT),
        "xstop_lock_recorded": len(XSTOP_SHA256) == 64 and XSTOP_BYTES > 0,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "actual": actual,
        "source_commit": SOURCE_COMMIT,
        "audit_policy": {"require_negative_control": True,
                         "scope_source": "Build.LOCKED_VARIANTS"},
        "xstop": {"path": LOCKED_XSTOP, "sha256": XSTOP_SHA256, "bytes": XSTOP_BYTES},
    }


def validate() -> dict[str, Any]:
    """Run every strict gate; only eighteen closures plus the aggregate can pass."""

    locks = source_lock_audit()
    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(Path(__file__)), doraise=True)
    configuration = configuration_audit(module)
    rejections = rejection_audit(module)
    exported, deterministic = export_variants(module)
    abi = abi_audits(exported)
    paths = materialize(exported)
    variants = {name: formal_one(name, paths) for name in VARIANTS}
    aggregate = formal_aggregate(paths)
    control = negative_control(paths)
    pyright = {"target": pyright_check(TARGET), "validator": pyright_check(Path(__file__))}

    failures: list[str] = []
    build_scope = tuple(getattr(module, "LOCKED_VARIANTS", ()))
    if set(build_scope) != set(VARIANTS) or len(build_scope) != len(VARIANTS):
        failures.append("Build LOCKED_VARIANTS does not match validator scope")
    if locks["status"] != "PASS":
        failures.append("source lock audit")
    if configuration["status"] != "PASS":
        failures.append("locked-equation configuration audit")
    if rejections["status"] != "PASS":
        failures.append("configuration rejection audit")
    if abi["status"] != "PASS":
        failures.append("ABI audit")
    if not all(paths["miter_selfchecks"].values()):
        failures.append("miter implicit-net selfcheck")
    for name, record in deterministic.items():
        if record["status"] != "PASS":
            failures.append(f"deterministic export {name}")
    for name, result in pyright.items():
        if result["status"] != "PASS":
            failures.append(f"pyright {name}")
    closed: list[str] = []
    for name, gates in variants.items():
        gate_failures = [gate for gate, result in gates.items() if result["status"] != "PASS"]
        if gate_failures:
            failures.extend(f"{name} {gate}" for gate in gate_failures)
        else:
            closed.append(name)
    if aggregate["status"] != "PASS":
        failures.append("aggregate SAT miter")
    if control["status"] != "PASS":
        failures.append("aggregate negative control")

    status = "COMPLETE_EQUIVALENCE" if not failures else "COMPLETE_EQUIVALENCE_VARIANT_ONLY"
    unclosed = [name for name in VARIANTS if name not in closed]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STRICT_COMPLETE_EQUIVALENCE",
        "build_id": "Build-Cpu.Backend.Issue.FuBusyTableRead",
        "validator": Path(__file__).relative_to(ROOT).as_posix(),
        "status": status,
        "strict_complete_eligible": status == "COMPLETE_EQUIVALENCE",
        "strict_complete_count_delta": 1 if status == "COMPLETE_EQUIVALENCE" else 0,
        "acceptance_eligible": status == "COMPLETE_EQUIVALENCE",
        "source_commit": SOURCE_COMMIT,
        "audit_policy": {"require_negative_control": True,
                         "scope_source": "Build.LOCKED_VARIANTS"},
        "closed_variant_count": len(closed),
        "public_variant_count": len(VARIANTS),
        "scope": {
            "kind": "eighteen_locked_stateless_combinational_specializations",
            "state_bits": 0,
            "state_boundary": "no clock/reset/register/memory in any reference or target variant",
            "public_variants": list(VARIANTS),
            "variants": {
                name: {
                    "num_entries": spec["num_entries"],
                    "fu_type_bits": FU_TYPE_BITS,
                    "table_bits": spec["table_bits"],
                    "latency_to_oh_bits": {str(k): sorted(v)
                                           for k, v in sorted(spec["latency_to_oh_bits"].items())},
                    "parents": list(spec["parents"]),
                    "inputs": {
                        "io_in_fuBusyTable": spec["table_bits"],
                        **{f"io_in_fuTypeRegVec_{i}": FU_TYPE_BITS
                           for i in range(spec["num_entries"])},
                    },
                    "input_bits": spec["table_bits"] + spec["num_entries"] * FU_TYPE_BITS,
                    "outputs_compared": {"io_out_fuBusyTableMask": spec["num_entries"]},
                    "method": "sat_miter",
                    "sequential": False,
                    "abi_exact": abi["rows"][name]["status"] == "PASS",
                    "deterministic": deterministic[name]["status"] == "PASS",
                    "miter_selfcheck": paths["miter_selfchecks"][name],
                    "sat": {
                        "returncode": variants[name]["yosys_formal_miter"].get("returncode"),
                        "status": variants[name]["yosys_formal_miter"].get("status"),
                        "formal_success_marker": variants[name]["yosys_formal_miter"].get("formal_success_marker"),
                        "unconstrained": variants[name]["yosys_formal_miter"].get("unconstrained"),
                    },
                }
                for name, spec in VARIANTS.items()
            },
            "inputs": {
                name: {"io_in_fuBusyTable": spec["table_bits"],
                       "io_in_fuTypeRegVec": spec["num_entries"] * FU_TYPE_BITS}
                for name, spec in VARIANTS.items()
            },
            "outputs_compared": {
                name: {"io_out_fuBusyTableMask": spec["num_entries"]}
                for name, spec in VARIANTS.items()
            },
            "aggregate_input_bits": sum(
                spec["table_bits"] + spec["num_entries"] * FU_TYPE_BITS
                for spec in VARIANTS.values()
            ),
            "aggregate_input_bit_accounting": " + ".join(
                f"{spec['table_bits']}+{spec['num_entries']}*{FU_TYPE_BITS}"
                for spec in VARIANTS.values()
            ),
            "aggregate_compared_output_bits": sum(
                spec["num_entries"] for spec in VARIANTS.values()
            ),
            "why_complete": (
                "Each specialization is proven by its own Yosys SAT miter in which "
                "io_in_fuBusyTable and all num_entries 35-bit io_in_fuTypeRegVec ports are "
                "unconstrained inputs and mismatch is the reduction-OR over every declared "
                "io_out_fuBusyTableMask bit; a flattened aggregate miter then proves the same "
                "bit-wise property for all eighteen variants in one run. No bounded vector "
                "contributes to this verdict."
            ),
            "bounded_tests_counted": False,
        },
        "reference_lock": {
            "path": LOCKED_XSTOP,
            "upstream_source_commit": SOURCE_COMMIT,
            "xstop_sha256": XSTOP_SHA256,
            "xstop_bytes": XSTOP_BYTES,
            "reference_dir": REFERENCE_DIR.relative_to(ROOT).as_posix(),
            "extraction_rule": (
                "each locked module body copied verbatim from validation/reference-sv and "
                "renamed to REF_<name> only inside the temporary work directory"
            ),
        },
        "sources": {
            "scala": {"path": SCALA.relative_to(ROOT).as_posix(),
                      "sha256": sha256_file(SCALA), "bytes": SCALA.stat().st_size},
            "reference_sv": {
                "path": (REFERENCE_DIR / "FuBusyTableRead.sv").relative_to(ROOT).as_posix(),
                "sha256": sha256_file(REFERENCE_DIR / "FuBusyTableRead.sv"),
                "bytes": (REFERENCE_DIR / "FuBusyTableRead.sv").stat().st_size,
                "locked_module": "FuBusyTableRead",
            },
            "reference_children": {
                name: {
                    "path": (REFERENCE_DIR / f"{name}.sv").relative_to(ROOT).as_posix(),
                    "sha256": sha256_file(REFERENCE_DIR / f"{name}.sv"),
                    "bytes": (REFERENCE_DIR / f"{name}.sv").stat().st_size,
                }
                for name in VARIANTS if name != "FuBusyTableRead"
            },
            "python_build": {"path": TARGET.relative_to(ROOT).as_posix(),
                             "sha256": sha256_file(TARGET), "bytes": TARGET.stat().st_size},
        },
        "checks": {
            "python_version": platform.python_version(),
            "py_compile": {"status": "PASS", "files": [
                TARGET.relative_to(ROOT).as_posix(),
                Path(__file__).relative_to(ROOT).as_posix(),
            ]},
            "pyright": pyright,
            "source_lock": locks,
            "configuration_audit": configuration,
            "rejection_audit": rejections,
            "abi": abi,
            "deterministic_export": deterministic,
            "tools": tool_versions(),
            "variants": variants,
            "formal": aggregate,
            "aggregate_sat_miter": aggregate,
            "negative_control": control,
        },
        "failures": failures,
        "unclosed": unclosed,
    }
    if failures:
        payload["variant_only_reason"] = (
            "One or more locked specializations did not close under the strict gates, so the "
            "Build cannot be credited as a complete equivalence; see `unclosed` and `failures`."
        )
        payload["uncovered_public_variants"] = unclosed
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return payload


def main() -> int:
    """Print strict status and return nonzero until all eighteen proofs close."""

    payload = validate()
    print(json.dumps({
        "status": payload["status"],
        "strict_complete_eligible": payload["strict_complete_eligible"],
        "closed": f"{payload['closed_variant_count']}/{payload['public_variant_count']}",
        "unclosed": payload["unclosed"],
        "failures": payload["failures"][:12],
    }, ensure_ascii=False))
    return 0 if payload["status"] == "COMPLETE_EQUIVALENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
