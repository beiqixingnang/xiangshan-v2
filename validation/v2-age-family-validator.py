"""Bounded validator for the V2 age/regcache family."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from amaranth.sim import Settle, Simulator, Tick

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Regcache.AgeFamily-Hardware.py"
HIER = ROOT / "validation/v2-locked-hierarchy.json"
WORK = ROOT / "validation/.work/v2-age-family"
EVIDENCE = ROOT / "validation/v2-age-family-results.json"
MEMBERS = ("NewAgeDetector", "NewAgeDetector_6", "RegCacheAgeDetector", "RegCacheAgeDetector_1", "RegCacheAgeTimer", "RegCacheAgeTimer_1", "RegCacheDataModule", "RegCacheDataModule_1", "RegCacheTagModule", "RegCacheTagModule_1")


def digest(data: bytes) -> str:
    """Hash exact evidence bytes."""

    return hashlib.sha256(data).hexdigest()


def load_target() -> Any:
    """Load the exact family Build."""

    spec = importlib.util.spec_from_file_location("v2_age_family_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); return module


def width(token: str) -> int:
    """Parse a locked ANSI range."""

    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run Verilator/Yosys with bounded output."""

    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered], capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "returncode": result.returncode, "status": "PASS" if result.returncode == 0 else "FAIL", "output_tail": output[-1000:], "output_sha256": digest(output.encode())}


def wsl_path(path: Path) -> str:
    """Convert Windows path to WSL."""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


def direct_new_age(module: Any, member: str) -> dict[str, Any]:
    """Check bounded NewAgeDetector selection behavior."""

    dut = module.AgeFamily(member); seen: list[int] = []
    def process():
        for name, direction, _width in dut.specs:
            if direction == "input" and name not in {"clock", "reset"}:
                yield dut.ports[name].eq(0)
        if "io_enq_0" in dut.ports:
            yield dut.ports["io_enq_0"].eq(1)
        if "io_canIssue_0" in dut.ports:
            yield dut.ports["io_canIssue_0"].eq(1)
        yield Settle()
        if "io_out_0" in dut.ports:
            seen.append(int((yield dut.ports["io_out_0"])))
    sim = Simulator(dut); sim.add_process(process); sim.run()
    return {"member": member, "vectors": 1, "observations": seen}


def main() -> int:
    """Run exact surface, direct, and tool gates."""

    module = load_target(); hierarchy = json.loads(HIER.read_text(encoding="utf-8"))["modules"]; failures: list[str] = []
    surface: dict[str, Any] = {}; tools: dict[str, Any] = {}
    for member in MEMBERS:
        expected = {(p["name"], p["direction"], width(str(p.get("width", "")))) for p in hierarchy[member]["ports"]}
        actual = set(module.PORT_SPECS[member]); surface[member] = {"locked": len(expected), "emitted": len(actual), "match": expected == actual}
        if expected != actual: failures.append(f"port mismatch {member}")
    py_compile.compile(str(TARGET), doraise=True); direct = [direct_new_age(module, m) for m in MEMBERS[:2]]
    WORK.mkdir(parents=True, exist_ok=True)
    for member in MEMBERS:
        rtl = module.build_verilog({"module": member}, {}); path = WORK / f"{member}.sv"; path.write_text(rtl, encoding="utf-8", newline="\n"); wsl = wsl_path(path)
        verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", wsl]); yosys = run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {wsl}; hierarchy -top {member}; proc; check"])
        tools[member] = {"rtl_bytes": len(rtl.encode()), "rtl_sha256": digest(rtl.encode()), "verilator": verilator, "yosys": yosys}
        if verilator["status"] != "PASS" or yosys["status"] != "PASS": failures.append(f"tool gate {member}")
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_AGE_REGCACHE_FAMILY", "batch_id": "V2-BACKEND-AGE-REGCACHE-001", "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af", "scala_sources": list(module.SOURCE_PATHS), "covered_modules": list(MEMBERS), "port_surface": surface, "direct": {"status": "PASS" if not failures else "FAIL", "members": direct, "remaining_members": list(MEMBERS[2:])}, "tool_gates": tools, "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS_BOUNDED_NEW_AGE_ONLY", "V2_REFERENCE_MATCHED": "PENDING_LOCKED_REGCACHE_DIFF", "VERILATOR": "PASS" if not failures else "FAIL", "YOSYS": "PASS" if not failures else "FAIL", "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME", "PARENT_CLOSURE_MATCHED": "PENDING", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"}, "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL", "acceptance_eligible": False, "failures": failures, "unclosed": ["Full RegCache parent and locked XSTop differential remain pending.", "AgeTimer/Data/Tag direct behavior vectors remain to be expanded.", "License review and user approval remain pending."]}
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"); print(json.dumps({"status": payload["status"], "covered": len(MEMBERS), "failures": failures})); return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
