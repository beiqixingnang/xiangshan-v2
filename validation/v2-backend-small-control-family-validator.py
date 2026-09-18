"""Bounded validator for the backend small-control aggregate.

The gate compares every aggregate member against the pinned V2 hierarchy,
checks deterministic Amaranth exports, and runs Verilator/Yosys lint.  It
intentionally records reference differential and parent integration as
pending; structural success is not behavioural equivalence.
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

# Resolve from the caller's repository cwd first; Windows code-page decoding
# can otherwise corrupt the non-ASCII workspace prefix in ``__file__``.
ROOT = Path.cwd() / ".agents" / "xiangshan-v2"
if not (ROOT / "V2-Snapshot.json").exists():
    ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.SmallControl.Family-Hardware.py"
LOCKED = ROOT / "validation/v2-locked-hierarchy.json"
RESULT = ROOT / "validation/v2-backend-small-control-family-results.json"
WORK = ROOT / "validation/.work/v2-backend-small-control-family"
TOOL_WORK = Path("C:/backend_small_control_family")
MEMBERS = (
    "AddrAddModule", "DatamoduleResultBuffer", "GPAMem", "RedirectGenerator", "RegCache",
    "RegCacheTagTable", "RegionWays", "RASStack", "FauFTBWay", "VectorCvtTop",
)
LOCKED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


def load_target() -> Any:
    """Load the exact aggregate target. / 加载精确聚合目标。"""

    spec = importlib.util.spec_from_file_location("backend_small_control_family", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def width(value: Any) -> int:
    """Normalize a locked Verilog width. / 规范化锁定 Verilog 位宽。"""

    text = str(value or "").strip()
    if text.startswith("[") and text.endswith("]") and ":" in text:
        high, low = text[1:-1].split(":", 1)
        return abs(int(high) - int(low)) + 1
    return 1


def tool(command: list[str]) -> dict[str, Any]:
    """Run one optional backend tool and retain a short result. / 运行后端工具并保留简短结果。"""

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "command": command,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "output_tail": (result.stdout + result.stderr)[-800:],
    }


# Convert a Windows path for the WSL tool bridge. / 将 Windows 路径转换为 WSL 工具路径。
def wsl_path(path: Path) -> str:
    """Return an absolute Linux path for a Windows file. / 返回 Windows 文件对应的绝对 Linux 路径。"""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def main() -> int:
    """Run bounded catalog/export/tool gates and write evidence. / 运行有界目录、导出与工具门禁并写证据。"""

    module = load_target()
    locked = json.loads(LOCKED.read_text(encoding="utf-8"))
    failures: list[str] = []
    if locked.get("reference_sha256") != LOCKED_SHA256:
        failures.append("locked hierarchy digest")
    py_compile.compile(str(TARGET), doraise=True)
    surfaces: dict[str, Any] = {}
    exports: dict[str, Any] = {}
    WORK.mkdir(parents=True, exist_ok=True)
    TOOL_WORK.mkdir(parents=True, exist_ok=True)
    for member in MEMBERS:
        expected = [
            (str(row["name"]), str(row["direction"]), width(row.get("width")))
            for row in locked["modules"][member]["ports"]
        ]
        actual = [(row.name, row.direction, row.width) for row in module.PORT_SPECS[member]]
        match = expected == actual
        surfaces[member] = {"locked": len(expected), "emitted": len(actual), "match": match}
        if not match:
            failures.append(f"port surface: {member}")
        source = module.build_verilog({"module": member}, {})
        repeat = module.build_verilog({"module": member}, {})
        deterministic = source == repeat
        if not deterministic:
            failures.append(f"nondeterministic export: {member}")
        path = WORK / f"{member}.sv"
        path.write_text(source, encoding="utf-8", newline="\n")
        tool_path = TOOL_WORK / f"{member}.sv"
        tool_path.write_text(source, encoding="utf-8", newline="\n")
        linux_path = wsl_path(tool_path)
        ver = tool(["wsl.exe", "-e", "verilator", "--lint-only", "-Wno-fatal", linux_path])
        yos = tool(["wsl.exe", "-e", "yosys", "-Q", "-p", f"read_verilog -sv {linux_path}; proc; check"])
        if ver["status"] != "PASS":
            failures.append(f"verilator: {member}")
        if yos["status"] != "PASS":
            failures.append(f"yosys: {member}")
        exports[member] = {
            "bytes": len(source.encode()),
            "sha256": hashlib.sha256(source.encode()).hexdigest(),
            "deterministic": deterministic,
            "verilator": ver,
            "yosys": yos,
        }
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_BACKEND_SMALL_CONTROL_FAMILY",
        "batch_id": "V2-BACKEND-SMALL-CONTROL-001",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "target": {"path": str(TARGET.relative_to(WORKSPACE)).replace("\\", "/"), "sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest()},
        "covered_modules": list(MEMBERS),
        "port_surface": surfaces,
        "exports": exports,
        "gates": {
            "PY_COMPILE": "PASS",
            "PORT_SURFACE": "PASS" if not any(x.startswith("port surface") for x in failures) else "FAIL",
            "DETERMINISTIC_EXPORT": "PASS" if not any(x.startswith("nondeterministic") for x in failures) else "FAIL",
            "VERILATOR": "PASS" if not any(x.startswith("verilator") for x in failures) else "FAIL",
            "YOSYS": "PASS" if not any(x.startswith("yosys") for x in failures) else "FAIL",
            "LOCKED_REFERENCE_IMMUTABLE": "PASS" if locked.get("reference_sha256") == LOCKED_SHA256 else "FAIL",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "VALIDATOR_PASS_BOUNDED" if not failures else "VALIDATOR_FAIL",
        "reference_differential": "PENDING_LOCKED_REFERENCE_DIFFERENTIAL",
        "parent_integration": "PENDING_USER_APPROVAL",
        "acceptance_eligible": False,
        "failures": failures,
        "unclosed": ["Reference differential, parent closure, and license review remain pending."],
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
