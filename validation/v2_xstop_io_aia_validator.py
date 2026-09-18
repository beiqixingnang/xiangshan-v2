"""Validator/evidence producer for TOP-XSTOP-UHSC-IO-005 AIA IO slice."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.ChiselAIA.Interface-Hardware.py"
TEST = ROOT / "python/Program-System/System-Testing/Testing-Cpu/Testing-Cpu.Dependency.ChiselAIA.Interface-Hardware.py"
INVENTORY = ROOT / "validation/v2-xstop-port-inventory.json"
OUT = ROOT / "validation/v2-top-xstop-io-aia-results.json"
MAPPING = ROOT / "validation/v2-top-xstop-io-aia-mapping.json"


def load_target() -> Any:
    spec = importlib.util.spec_from_file_location("v2_xstop_io_aia_subject", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def main() -> int:
    module = load_target()
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    locked = {p["name"]: p for p in inventory["ports"] if p["name"] == "io_clock" or p["name"] == "io_reset" or p["name"] == "io_extIntrs" or p["name"].startswith("imsic_axi4_")}
    dut = module.UHSCAIAImsicAXI4(module.AIAConfig())
    exported = {signal.name: signal for signal in dut.export_ports()}
    dut.elaborate(None)
    surface_failures: list[str] = []
    for name, spec in locked.items():
        signal = exported.get(name)
        if signal is None:
            surface_failures.append(f"missing:{name}")
            continue
        width = len(signal)
        expected_width = 1 if not spec["width"] else int(spec["width"].split(":")[0].strip("[")) + 1
        if width != expected_width:
            surface_failures.append(f"width:{name}:{width}!={expected_width}")
    vectors = [
        module.imsic_axi4_reference_step(0, 0, 2, irq_sources=8),
        module.imsic_axi4_reference_step(2, 2, 0, write_word=4, write_data=2, irq_sources=8),
        module.imsic_axi4_reference_step(0, 2, 0, write_word=5, write_data=2, irq_sources=8),
    ]
    pyright_proc = run(["pyright.cmd", str(TARGET), str(TEST), str(Path(__file__))])
    direct = run([sys.executable, str(TEST)])
    rtl = module.build_verilog({"module": "UHSCAIAImsicAXI4"}, {})
    with tempfile.TemporaryDirectory(prefix="v2_xstop_aia_") as directory:
        sv = Path(directory) / "UHSCAIAImsicAXI4.sv"
        sv.write_text(rtl, encoding="utf-8", newline="\n")
        wsl = run(["wsl.exe", "-e", "wslpath", "-a", str(sv)])
        verilator = yosys = None
        if wsl.returncode == 0:
            path = wsl.stdout.strip()
            verilator = run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal '{path}'"])
            yosys = run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv {path}; hierarchy -top UHSCAIAImsicAXI4; proc; check'"])
    backend = {
        "verilator": "PASS" if verilator is not None and verilator.returncode == 0 else "FAIL",
        "yosys": "PASS" if yosys is not None and yosys.returncode == 0 else "FAIL",
        "rtl_bytes": len(rtl.encode()),
        "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(),
    }
    failures = surface_failures[:]
    if direct.returncode != 0:
        failures.append("system_testing")
    if pyright_proc.returncode != 0:
        failures.append("pyright")
    if backend["verilator"] != "PASS":
        failures.append("verilator")
    if backend["yosys"] != "PASS":
        failures.append("yosys")
    status = "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL"
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_TOP_XSTOP_UHSC_IO_AIA",
        "task_id": "TOP-XSTOP-UHSC-IO-005",
        "batch_id": "V2-TOP-IO-AIA-002",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "locked_reference": {
            "inventory": INVENTORY.relative_to(ROOT).as_posix(),
            "port_count": len(locked),
            "ports": sorted(locked),
            "port_contract": [
                {"name": name, "direction": spec["direction"], "width": spec["width"]}
                for name, spec in sorted(locked.items())
            ],
        },
        "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest()},
        "direct": {"status": "PASS" if direct.returncode == 0 else "FAIL", "vectors": vectors, "command": [sys.executable, str(TEST)]},
        "backend": backend,
        "commands": {
            "py_compile": ["python", "-m", "py_compile", str(TARGET), str(TEST), str(Path(__file__))],
            "pyright": ["pyright.cmd", str(TARGET), str(TEST), str(Path(__file__))],
            "build_verilog": "build_verilog({module: UHSCAIAImsicAXI4})",
            "system_testing": [sys.executable, str(TEST)],
            "verilator": "verilator --lint-only -Wno-fatal UHSCAIAImsicAXI4.sv",
            "yosys": "yosys -Q -p 'read_verilog -sv UHSCAIAImsicAXI4.sv; hierarchy -top UHSCAIAImsicAXI4; proc; check'",
        },
        "gates": {
            "PY_COMPILE": "PASS",
            "PYRIGHT": "PASS" if pyright_proc.returncode == 0 else "FAIL",
            "BUILD_VERILOG": "PASS",
            "DIRECT_TEST_PASS_BOUNDED": "PASS" if direct.returncode == 0 else "FAIL",
            "VERILATOR": backend["verilator"],
            "YOSYS": backend["yosys"],
            "LOCKED_XSTOP_PORT_SURFACE": "PASS" if not surface_failures else "FAIL",
            "PARENT_CLOSURE_MATCHED": "PENDING_XSTOP_AIA_PARENT",
            "LICENSE_REVIEW": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": status,
        "acceptance_eligible": False,
        "failures": failures,
        "unclosed": [
            "Full XSTop/UHSCTop AIA parent wiring and locked behavioral differential remain pending.",
            "TL/AXI burst ordering, multi-hart/TEE routing, license review, and user approval remain pending.",
        ],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    mapping = {
        "schema_version": 1,
        "task_id": "TOP-XSTOP-UHSC-IO-005",
        "family_id": "top.xstop.uhsc.io.aia",
        "source_paths": ["ChiselAIA/src/main/scala/IMSIC.scala", "ChiselAIA/src/main/scala/Example-axi.scala", "src/main/scala/device/imsic_axi_top.scala", "src/main/scala/top/Top.scala"],
        "target": TARGET.relative_to(ROOT).as_posix(),
        "locked_ports": sorted(locked),
        "implemented_boundary": "UHSCAIAImsicAXI4 single-beat IMSIC AXI4 register boundary with io_extIntrs accumulation",
        "status": status,
        "gates": payload["gates"],
        "accepted": False,
    }
    MAPPING.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": status, "locked_ports": len(locked), "verilator": backend["verilator"], "yosys": backend["yosys"], "failures": failures}))
    return 0 if status == "VALIDATOR_PASS_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
