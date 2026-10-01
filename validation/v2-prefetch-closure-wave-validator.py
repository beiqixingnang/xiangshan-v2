"""Bounded Prefetch family implementation and backend gate receipt.

This wave records executable members and keeps locked differential/formal
pending until the coordinator runs the serialized strict rail.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import py_compile
import shlex
import subprocess
import sys
import tempfile
from typing import Any

from v2_strict_family_rail import declared_ports, load_module, wsl_path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Cpu-Memory-Memory.Prefetch.Family-Hardware.py"
DIRECT = ROOT / "python/Program-System/System-Testing/Testing-Cpu/Testing-Cpu-Memory.Prefetch.Family-Hardware.py"
REFERENCE_DIR = ROOT / "validation/reference-sv"
EVIDENCE = ROOT / "validation/v2-prefetch-closure-wave-results.json"
MEMBERS = ("ActiveGenerationTable", "PrefetchFilter", "SMSTrainFilter", "StridePF",
           "MutiLevelPrefetchFilter", "TrainFilter", "TrainFilter_1", "BloomFilter", "CounterFilter")
IMPLEMENTED = ("SMSTrainFilter", "TrainFilter", "TrainFilter_1", "BloomFilter", "CounterFilter")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tool(command: list[str], top: str, path: Path) -> dict[str, Any]:
    linux = wsl_path(path)
    if command[0] == "verilator":
        command = command + ["--top-module", top, linux]
    else:
        command = command + ["-Q", "-p", f"read_verilog -sv {linux}; hierarchy -check -top {top}; proc; stat; check"]
    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                            capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"status": "PASS" if result.returncode == 0 else "FAIL", "returncode": result.returncode,
            "command": command, "output_tail": output[-1800:], "output_sha256": digest(output.encode())}


def main() -> int:
    module = load_module("prefetch_closure_wave", TARGET)
    py_compile.compile(str(TARGET), doraise=True)
    py_compile.compile(str(DIRECT), doraise=True)
    direct = subprocess.run([sys.executable, "-B", str(DIRECT.relative_to(ROOT))], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
                            timeout=240)
    work = Path(tempfile.mkdtemp(prefix="uhsc_prefetch_closure_"))
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for member in MEMBERS:
        if member not in IMPLEMENTED:
            rows.append({"member": member, "implemented": False,
                         "status": "CONTRACT_ONLY", "strict_status": "STRICT_PENDING"})
            continue
        first = module.build_verilog({"module": member}, {})
        second = module.build_verilog({"module": member}, {})
        target = work / f"{member}.sv"
        target.write_text(first, encoding="utf-8", newline="\n")
        locked = REFERENCE_DIR / f"{member}.sv"
        expected = declared_ports(locked.read_text(encoding="utf-8"), member) if locked.is_file() else {}
        actual = declared_ports(first, member)
        abi = bool(expected) and expected == actual
        ver = tool(["verilator", "--lint-only", "-Wno-fatal"], member, target)
        yosys = tool(["yosys"], member, target)
        row = {"member": member, "implemented": member in IMPLEMENTED,
               "deterministic": first == second, "bytes": len(first.encode()),
               "rtl_sha256": digest(first.encode()), "abi": abi,
               "verilator": ver, "yosys": yosys,
               "status": "IMPLEMENTED_UNVERIFIED" if member in IMPLEMENTED else "CONTRACT_ONLY"}
        rows.append(row)
        if member in IMPLEMENTED and (not row["deterministic"] or not abi or ver["status"] != "PASS" or yosys["status"] != "PASS"):
            failures.append(member)
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_PREFETCH_CLOSURE_WAVE",
               "batch_id": "V2-PREFETCH-CLOSURE-WAVE-001", "target": str(TARGET.relative_to(ROOT)).replace("\\", "/"),
               "build_sha256": digest(TARGET.read_bytes()), "members": rows,
               "implemented_members": list(IMPLEMENTED), "contract_only_members": [m for m in MEMBERS if m not in IMPLEMENTED],
               "direct": {"status": "PASS" if direct.returncode == 0 else "FAIL", "returncode": direct.returncode,
                          "output_tail": (direct.stdout + direct.stderr)[-1800:]},
               "gates": {"PY_COMPILE": "PASS", "DIRECT": "PASS" if direct.returncode == 0 else "FAIL",
                         "IMPLEMENTED_ABI_BACKENDS": "PASS" if not failures else "FAIL",
                         "LOCKED_REFERENCE_DIFFERENTIAL": "STRICT_PENDING",
                         "FORMAL": "PENDING_ROOT_SERIAL_RAIL", "PARENT_CLOSURE": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
               "status": "IMPLEMENTED_UNVERIFIED_STRICT_PENDING" if direct.returncode == 0 and not failures else "FAIL",
               "strict_delta": 0, "acceptance_eligible": False,
               "unclosed": ["Locked reference differential/formal, full family, parent closure, license and acceptance remain pending."],
               "failures": failures}
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "direct": payload["direct"]["status"], "implemented": list(IMPLEMENTED), "failures": failures}))
    return 0 if payload["status"].startswith("IMPLEMENTED_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
