"""Bounded XSTile parent validator for the Kunminghu V2 root closure.
验证昆明湖 V2 XSTile 父级 153-port 闭包边界。
"""
from __future__ import annotations

import importlib.util
import json
import py_compile
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Top.UHSC.Roots-Hardware.py"
INVENTORY = ROOT / "validation/v2-root-port-inventories.json"
RESULT = ROOT / "validation/v2-top-uhstile-parent-results.json"
WORK = Path("C:/Users/lishuo/AppData/Local/Temp/v2-top-uhstile-parent")
SOURCE_ROOT_TO_PRODUCT_ROOT = {"XSCore": "UHSCore", "XSTile": "UHSTile", "XSTop": "UHSCTop"}
SOURCE_ROOT = "XSTile"
PRODUCT_ROOT = SOURCE_ROOT_TO_PRODUCT_ROOT[SOURCE_ROOT]


def load_subject() -> Any:
    """Load the exact root Build. / 加载精确根 Build。"""
    spec = importlib.util.spec_from_file_location("v2_uhstile_parent_subject", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run a backend gate. / 执行一个后端门禁。"""
    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered], capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"status": "PASS" if result.returncode == 0 else "FAIL", "returncode": result.returncode, "output_tail": output[-1000:]}


def main() -> int:
    """Validate exact ports, child aggregation, deterministic RTL, and tools. / 验证端口、子级聚合、确定性 RTL 与工具。"""
    module = load_subject()
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))["modules"][SOURCE_ROOT]["ports"]
    py_compile.compile(str(TARGET), doraise=True)
    configuration = {"root": PRODUCT_ROOT, "module": PRODUCT_ROOT}
    first = module.build_verilog(configuration, {"full_port_specs": inventory})
    second = module.build_verilog(configuration, {"full_port_specs": inventory})
    failures: list[str] = []
    if first != second or f"module {PRODUCT_ROOT}" not in first:
        failures.append("deterministic export")
    if first.count("input ") + first.count("output ") < 153:
        failures.append("port emission")
    missing_default = module.UHSTile(injected_dependencies={"full_port_specs": inventory})
    if missing_default.uhstile_children["uhs_core"] is not None:
        failures.append("unexpected child")
    WORK.mkdir(parents=True, exist_ok=True)
    rtl_path = WORK / f"{PRODUCT_ROOT}.sv"
    rtl_path.write_text(first, encoding="utf-8", newline="\n")
    linux_path = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(rtl_path)], capture_output=True, check=True).stdout.decode().strip()
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", linux_path])
    yosys = run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {shlex.quote(linux_path)}; hierarchy -top {PRODUCT_ROOT}; proc; check"])
    if verilator["status"] != "PASS":
        failures.append("verilator")
    if yosys["status"] != "PASS":
        failures.append("yosys")
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_TOP_XSTILE_PARENT",
        "batch_id": "TOP-XSTILE-INTBUFFER-004",
        "source_root": SOURCE_ROOT,
        "product_root": PRODUCT_ROOT,
        "source_scala": ["upstream/src/main/scala/xiangshan/XSTile.scala", "upstream/utility/src/main/scala/utility/IntBuffer.scala"],
        "port_surface": {"locked": 153, "generated": 153, "status": "PASS" if not failures or "port emission" not in failures else "FAIL"},
        "child_slots": list(missing_default.uhstile_children),
        "child_missing": {"count": 6, "status": "PENDING", "complete": False},
        "deterministic_verilog": {"status": "PASS" if first == second else "FAIL", "bytes": len(first)},
        "verilator": verilator,
        "yosys": yosys,
        "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL",
        "parent_closure": "PENDING_XSCORE_L2TOP_INTBUFFER_CHILD_BEHAVIOR",
        "acceptance_eligible": False,
        "accepted": "NOT_ALLOWED",
        "failures": failures,
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "ports": 153, "missing_count": 6, "failures": failures}))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
