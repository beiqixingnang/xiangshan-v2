"""Focused closure validator for the UopInfoGen Decode leaf.

This validator owns only the UopInfoGen member of the Decode.Control family.
It records the locked XSTop identity in evidence, while keeping all provenance
out of the executable Build.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Backend.Decode.ControlFamily-Hardware.py"
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
WORK = ROOT / "validation/.work/v2-backend-closure-wave-uopinfo"
EVIDENCE = ROOT / "validation/v2-backend-closure-wave-uopinfo.json"
LOCKED_XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
SOURCE = ROOT / "upstream/src/main/scala/xiangshan/backend/decode/UopInfoGen.scala"


def load_target() -> Any:
    spec = importlib.util.spec_from_file_location("v2_uopinfo_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run(command: list[str]) -> dict[str, object]:
    result = subprocess.run(command, capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {
        "command": command,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "output_tail": output[-1200:],
    }


def wsl_path(path: Path) -> str:
    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


def direct_vectors(module: Any) -> bool:
    vectors = (
        ("VEC_VVV", 1, 0, 0, 0, 0, False, False, (2, 2, 2)),
        ("VEC_RGATHER", 3, 0, 0, 0, 0, False, False, (64, 64, 8)),
        ("VEC_I_LDST", 1, 0, 0, 1, 0, False, False, (5, 5, 2)),
        ("AMO_CAS_Q", 0, 0, 0, 0, 0, False, False, (4, 2, 1)),
        ("VEC_US_LDST", 1, 0, 0, 0, 0, True, False, (2, 2, 2)),
    )
    for name, vlmul, vsew, vwidth, nf, vmvn, is_vlsr, is_vlsm, expected in vectors:
        actual = module.uop_info_reference(
            module.UOP_SPLIT_CODES[name], vsew, vlmul, vwidth,
            nf, vmvn, is_vlsr, is_vlsm,
        )
        if actual != expected:
            return False
    return True


def main() -> int:
    module = load_target()
    failures: list[str] = []
    py_compile.compile(str(TARGET), doraise=True)
    if tuple(module.IMPLEMENTED_MEMBERS) != ("UopInfoGen",):
        failures.append("implemented-member declaration mismatch")
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))["modules"]["UopInfoGen"]
    expected = {(str(port["name"]), str(port["direction"])) for port in hierarchy["ports"]}
    actual = {(str(name), str(direction)) for name, direction, _width in module.PORT_SPECS["UopInfoGen"]}
    if expected != actual:
        failures.append("UopInfoGen port names/directions differ from locked hierarchy")
    direct = direct_vectors(module)
    if not direct:
        failures.append("direct equation vectors failed")
    first = module.build_verilog({"module": "UopInfoGen"}, {})
    second = module.build_verilog({"module": "UopInfoGen"}, {})
    deterministic = first == second
    if not deterministic:
        failures.append("same-name export is not deterministic")
    WORK.mkdir(parents=True, exist_ok=True)
    rtl_path = WORK / "UopInfoGen.sv"
    rtl_path.write_text(first, encoding="utf-8", newline="\n")
    linux = wsl_path(rtl_path)
    verilator = run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{linux}'"])
    yosys = run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p \"read_verilog -sv '{linux}'; proc; check\""])
    if verilator["status"] != "PASS":
        failures.append("Verilator lint failed")
    if yosys["status"] != "PASS":
        failures.append("Yosys check failed")
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest() if SOURCE.exists() else None
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_CLOSURE_WAVE_UOPINFO",
        "batch_id": "V2-BACKEND-CLOSURE-WAVE-001",
        "member": "UopInfoGen",
        "build_path": str(TARGET.relative_to(ROOT)).replace("\\", "/"),
        "build_sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest(),
        "scala_source": "upstream/src/main/scala/xiangshan/backend/decode/UopInfoGen.scala",
        "scala_source_sha256": source_hash,
        "locked_reference": {"canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv", "sha256": LOCKED_XSTOP_SHA256},
        "port_abi": {"locked": len(expected), "emitted": len(actual), "match": expected == actual},
        "direct_test": {"status": "PASS_BOUNDED" if direct else "FAIL", "vectors": 5},
        "export": {"status": "PASS" if deterministic else "FAIL", "bytes": len(first.encode()), "sha256": hashlib.sha256(first.encode()).hexdigest()},
        "tool_gates": {"py_compile": "PASS", "verilator": verilator, "yosys": yosys},
        "gates": {"DIRECT_TEST_PASS_BOUNDED": "PASS_BOUNDED", "V2_REFERENCE_MATCHED": "STRICT_PENDING", "PARENT_CLOSURE_MATCHED": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
        "status": "DIRECT_TEST_PASS_BOUNDED" if not failures else "FAIL",
        "acceptance_eligible": False,
        "failures": failures,
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "member": "UopInfoGen", "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
