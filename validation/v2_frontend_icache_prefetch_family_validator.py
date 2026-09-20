"""Validator for the missing front-end ICache/prefetch aggregate.

This is intentionally a bounded gate: it checks the exact locked port tables,
Python/pyright importability, deterministic Build exports, and Verilator/Yosys
elaboration for all seven members.  Full locked-reference differential and
parent closure are recorded as pending rather than implied by these checks.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from v2_build_provenance import source_paths_for_build

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Icache.Prefetch.Family-Hardware.py"
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
EVIDENCE = ROOT / "validation/v2-frontend-icache-prefetch-family-results.json"
WORK = ROOT / "validation/.work/v2-frontend-icache-prefetch-family"
# WSL's Windows-codepage bridge can mangle the Chinese workspace prefix when a
# Yosys command line carries a long path.  Keep a second, ASCII-only tool
# staging directory; the generated evidence still points at the immutable
# workspace target and records hashes from the same bytes.
TOOL_WORK = Path("C:/v2_icache_prefetch_family")
MEMBERS = (
    "ICacheMainPipe",
    "IPrefetchPipe",
    "WayLookup",
    "InstrMMIOEntry",
    "L2TlbPrefetch",
    "L2TlbMissQueue",
    "PrefetcherMonitor",
)
LOCKED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


def _load_target() -> Any:
    spec = importlib.util.spec_from_file_location("v2_frontend_icache_prefetch_family", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _wsl_path(path: Path) -> str:
    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path.resolve())], capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


def _tool(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, capture_output=True, check=False)
    text = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "status": "PASS" if result.returncode == 0 else "FAIL", "returncode": result.returncode, "output_tail": text[-1200:]}


def _run() -> int:
    module = _load_target()
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))
    locked = hierarchy["modules"]
    WORK.mkdir(parents=True, exist_ok=True)
    TOOL_WORK.mkdir(parents=True, exist_ok=True)

    py_compile.compile(str(TARGET), doraise=True)
    port_records: list[dict[str, Any]] = []
    failures: list[str] = []
    for name in MEMBERS:
        expected = {
            (str(row["name"]), str(row["direction"]), module._width(row.get("width")))
            for row in locked[name]["ports"]
        }
        actual = set(module.PORT_SPECS[name])
        match = expected == actual
        if not match:
            failures.append(f"port mismatch: {name}")
        port_records.append({"module": name, "locked": len(expected), "emitted": len(actual), "match": match})

    exports: dict[str, Any] = {}
    for name in MEMBERS:
        first = module.build_verilog({"module": name}, {})
        second = module.build_verilog({"module": name}, {})
        deterministic = first == second
        if not deterministic:
            failures.append(f"non-deterministic export: {name}")
        path = WORK / f"{name}.sv"
        path.write_text(first, encoding="utf-8", newline="\n")
        tool_path = TOOL_WORK / f"{name}.sv"
        tool_path.write_text(first, encoding="utf-8", newline="\n")
        linux = _wsl_path(tool_path)
        verilator = _tool(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{linux}'"])
        # Amaranth's synthesis-hint attributes are accepted by Verilator but
        # not by the bundled Yosys parser; remove only those hint lines.
        cleaned = TOOL_WORK / f"yosys-{name}.sv"
        cleaned.write_text("\n".join(line for line in first.splitlines() if "full_case" not in line and "parallel_case" not in line) + "\n", encoding="utf-8", newline="\n")
        yosys_linux = _wsl_path(cleaned)
        yosys = _tool(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p \"read_verilog -sv '{yosys_linux}'; proc; check\""])
        if verilator["status"] != "PASS":
            failures.append(f"Verilator: {name}")
        if yosys["status"] != "PASS":
            failures.append(f"Yosys: {name}")
        exports[name] = {
            "bytes": len(first.encode()),
            "sha256": hashlib.sha256(first.encode()).hexdigest(),
            "deterministic": deterministic,
            "verilator": verilator,
            "yosys": yosys,
        }

    pyright_command = next(
        (candidate for candidate in ("pyright.cmd", "pyright") if shutil.which(candidate)),
        None,
    )
    if pyright_command is None:
        # PowerShell exposes the bundled npm launcher as a .ps1 script, which
        # is not directly executable through CreateProcess on Windows.
        ps1 = Path.home() / "AppData/Roaming/npm/pyright.ps1"
        pyright = (
            _tool(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1), str(TARGET)])
            if ps1.exists()
            else {"status": "SKIPPED", "reason": "pyright executable not found"}
        )
    else:
        pyright = _tool([pyright_command, str(TARGET)])
    if pyright.get("status") != "PASS":
        failures.append("Pyright")

    locked_ok = hierarchy.get("reference_sha256") == LOCKED_SHA256
    if not locked_ok:
        failures.append("locked hierarchy digest")
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_ICACHE_PREFETCH_FAMILY",
        "batch_id": "V2-FRONTEND-ICACHE-PREFETCH-MISSING-001",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest()},
        "scala_sources": list(source_paths_for_build(TARGET)),
        "covered_modules": list(MEMBERS),
        "port_surface": {"status": "PASS" if not any(not x["match"] for x in port_records) else "FAIL", "modules": port_records},
        "py_compile": "PASS",
        "pyright": pyright,
        "exports": exports,
        "locked_reference": {"canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv", "xstop_sha256": LOCKED_SHA256, "immutable": locked_ok},
        "system_testing": {"manifest": "Program-System/System-Testing/Manifest-Testing-Hardware.py", "status": "NOT_REGISTERED_AGGREGATE_DIRECT_TEST"},
        "gates": {
            "PY_COMPILE": "PASS",
            "PYRIGHT": pyright.get("status", "FAIL"),
            "PORT_SURFACE": "PASS" if not failures or not any(x.startswith("port mismatch") for x in failures) else "FAIL",
            "BUILD_VERILOG": "PASS" if not any(x.startswith("non-deterministic") for x in failures) else "FAIL",
            "VERILATOR": "PASS" if not any(x.startswith("Verilator") for x in failures) else "FAIL",
            "YOSYS": "PASS" if not any(x.startswith("Yosys") for x in failures) else "FAIL",
            "V2_LOCKED_REFERENCE_IMMUTABLE": "PASS" if locked_ok else "FAIL",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "failures": failures,
        "unclosed": [
            "Locked-reference behavioural differential for the seven aggregate members remains pending.",
            "ICache parent closure and System-Testing direct registration remain coordinator obligations.",
            "License review and user acceptance remain pending.",
        ],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "failures": failures}, ensure_ascii=False))
    return 0 if payload["status"] == "VALIDATOR_PASS_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(_run())
