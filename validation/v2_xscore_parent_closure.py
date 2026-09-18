"""Independent validator for the bounded XSCore parent bridge.

The validator joins the immutable 308-port inventory with the source-backed
Frontend/Backend/MemBlock bridge. It proves exact structural export,
bounded parent equations, and host/WSL syntax gates while preserving the
real child-missing state. It never promotes this bridge to full XSCore closure.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from amaranth.sim import Settle, Simulator


# =============================================================================
# Module Contract
# =============================================================================
# Source authority is XSCore.scala plus the three explicit child parent
# boundaries. The locked XSTop snapshot and 308-port inventory are immutable.
# 本验证器以 XSCore.scala 及三个显式子级父边界为源码权威；锁定 XSTop 快照和
# 308 端口清单不可变更。
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Top.XSCore.Parent-Hardware.py"
INVENTORY = ROOT / "validation/v2-root-port-inventories.json"
SOURCE = ROOT / "upstream/src/main/scala/xiangshan/XSCore.scala"
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
WORK = ROOT / "validation/.work/v2-xscore-parent"
RESULT = ROOT / "validation/v2-xscore-parent-results.json"
DIRECT_RESULT = ROOT / "validation/v2-xscore-parent-direct-results.json"
DIFF_RESULT = ROOT / "validation/v2-xscore-parent-differential-results.json"
CONTRACT_RESULT = ROOT / "validation/v2-xscore-parent-contract-audit.json"
COVERAGE_RESULT = ROOT / "validation/v2-xscore-parent-coverage-manifest.json"
MAPPING_RESULT = ROOT / "validation/v2-xscore-parent-mapping-update.json"
PORT_RESULT = ROOT / "validation/v2-xscore-parent-port-inventory.json"


# =============================================================================
# Configuration
# =============================================================================
CHILD_TARGETS = {
    "frontend": ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Top-Hardware.py",
    "backend": ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Top-Hardware.py",
    "mem_block": ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.MemBlock-Hardware.py",
}
CHILD_SOURCES = {
    "frontend": "upstream/src/main/scala/xiangshan/frontend/Frontend.scala",
    "backend": "upstream/src/main/scala/xiangshan/backend/Backend.scala",
    "mem_block": "upstream/src/main/scala/xiangshan/mem/MemBlock.scala",
}


# =============================================================================
# Implementation
# =============================================================================
def digest_bytes(value: bytes) -> str:
    """Hash exact bytes without normalization. / 对原始字节计算摘要而不规范化。"""

    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    """Hash one local path. / 计算本地路径摘要。"""

    return digest_bytes(path.read_bytes())


def load_exact(path: Path, name: str) -> Any:
    """Load a hyphenated Build file by exact path. / 按精确路径加载带连字符的 Build 文件。"""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def inventory_rows() -> list[dict[str, Any]]:
    """Read and validate the locked XSCore rows. / 读取并校验锁定 XSCore 清单。"""

    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
    if payload.get("source_commit") != SOURCE_COMMIT or payload.get("reference_sha256") != REFERENCE_SHA256:
        raise RuntimeError("XSCore inventory baseline mismatch")
    rows = payload.get("modules", {}).get("XSCore", {}).get("ports", [])
    if not isinstance(rows, list) or len(rows) != 308:
        raise RuntimeError("XSCore inventory must contain 308 rows")
    return [dict(row) for row in rows]


def width(value: Any) -> int:
    """Normalize a Verilog width. / 规范化 Verilog 位宽。"""

    if isinstance(value, str) and ":" in value:
        nums = re.findall(r"\d+", value)
        if len(nums) == 2:
            return abs(int(nums[0]) - int(nums[1])) + 1
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def generated_ports(rtl: str, module_name: str) -> dict[str, tuple[str, int]]:
    """Parse ANSI declarations from generated SystemVerilog. / 解析生成 SystemVerilog 的 ANSI 声明。"""

    start = rtl.find(f"module {module_name}(")
    if start < 0:
        raise AssertionError(f"missing generated module {module_name}")
    end = rtl.find("endmodule", start)
    declarations: dict[str, tuple[str, int]] = {}
    for line in rtl[start:end].splitlines():
        match = re.match(r"\s*(input|output|inout)(?:\s+\[(\d+):0\])?\s+(.+);\s*$", line)
        if match is None:
            continue
        direction, high, names = match.groups()
        port_width = int(high) + 1 if high else 1
        for name in names.split(","):
            clean = name.strip().replace("\\", "")
            if clean:
                declarations[clean] = (direction, port_width)
    return declarations


def static_audit(path: Path) -> dict[str, Any]:
    """Run the five-zone and no-cross-import audit. / 执行五区及禁止跨文件导入审计。"""

    raw = path.read_bytes()
    text = raw.decode("utf-8")
    tree = ast.parse(text, filename=str(path))
    lines = text.splitlines()
    zones = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
    positions = [text.find(zone) for zone in zones]
    comments: list[str] = []
    forbidden: list[str] = []
    cross_build: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            previous = lines[node.lineno - 2].strip() if node.lineno > 1 else ""
            if not previous.startswith("#") and not (node.body and isinstance(node.body[0], ast.Expr)):
                comments.append(f"{node.name}:{node.lineno}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in {"socket", "urllib", "runpy"}:
                    forbidden.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in {"socket", "urllib", "runpy"}:
                forbidden.append(node.module)
            if "Build-Cpu" in node.module:
                cross_build.append(f"{node.lineno}:{node.module}")
    adapter = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    args = [arg.arg for arg in adapter[0].args.args] if len(adapter) == 1 else []
    passed = (
        positions == sorted(positions) and all(item >= 0 for item in positions)
        and args == ["configuration", "injected_dependencies"]
        and not comments and not forbidden and not cross_build
        and not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw
    )
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": digest_bytes(raw),
        "bytes": len(raw),
        "zones": positions,
        "adapter_args": args,
        "function_comment_errors": comments,
        "forbidden_imports": forbidden,
        "cross_build_imports": cross_build,
        "status": "PASS" if passed else "FAIL",
    }


def wsl_path(path: Path) -> str:
    """Map an auxiliary path to WSL. / 将辅助路径映射为 WSL 路径。"""

    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    tail = str(resolved).replace("\\", "/")[2:]
    return f"/mnt/{drive}{tail}"


def run_wsl(command: str) -> dict[str, Any]:
    """Run one WSL tool command and retain a digest. / 运行 WSL 工具并保留摘要。"""

    try:
        result = subprocess.run(
            ["wsl.exe", "-e", "bash", "-lc", command],
            capture_output=True, timeout=300, check=False,
        )
        output = (result.stdout + result.stderr).decode("utf-8", "replace")
        return {
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "returncode": result.returncode,
            "output_tail": output[-1800:],
            "output_sha256": digest_bytes(output.encode("utf-8")),
            "command": command,
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        text = str(error)
        return {"status": "FAIL", "returncode": None, "output_tail": text,
                "output_sha256": digest_bytes(text.encode()), "command": command}


def direct_probe(module: Any) -> dict[str, Any]:
    """Check missing-child diagnostics and bounded equations. / 检查缺子级诊断及有界方程。"""

    top = module.XSCoreParent()
    observed: dict[str, int] = {}

    def process():
        yield top.reset.eq(1)
        yield Settle()
        observed.update({
            "child_missing": (yield top.child_missing),
            "child_missing_count": (yield top.child_missing_count),
            "closure_missing": (yield top.closure_missing),
            "closure_complete": (yield top.closure_complete),
        })

    simulator = Simulator(top)
    simulator.add_process(process)
    simulator.run()
    expected = module.xs_core_parent_observation(
        frontend_valid=True, backend_can_accept=True,
        mem_a_valid=True, mem_a_ready=True,
        mem_d_valid=True, mem_d_ready=True,
        child_missing=3,
    )
    return {
        "status": "PASS" if observed == {
            "child_missing": 7, "child_missing_count": 3,
            "closure_missing": 1, "closure_complete": 0,
        } else "FAIL",
        "observed": observed,
        "expected_missing_mask": 7,
        "equation_probe": expected,
        "child_missing_semantics": "three bounded/injected child closures remain missing until explicit PASS_COMPLETE status",
    }


def differential_probe(module: Any) -> dict[str, Any]:
    """Exercise deterministic parent observation vectors. / 执行确定性父级观测向量。"""

    vectors: list[dict[str, int]] = []
    mismatches: list[dict[str, Any]] = []
    for index in range(32):
        vector = {
            "frontend_valid": index % 3 != 0,
            "backend_can_accept": index % 4 != 0,
            "mem_a_valid": index % 5 != 0,
            "mem_a_ready": index % 6 != 0,
            "mem_d_valid": index % 7 == 0,
            "mem_d_ready": index % 2 == 0,
            "reset": index < 2,
            "child_missing": 3,
        }
        got = module.xs_core_parent_observation(**vector)
        expected = {
            "frontend_backend_fire": int(vector["frontend_valid"] and vector["backend_can_accept"] and not vector["reset"]),
            "mem_a_fire": int(vector["mem_a_valid"] and vector["mem_a_ready"] and not vector["reset"]),
            "mem_d_fire": int(vector["mem_d_valid"] and vector["mem_d_ready"] and not vector["reset"]),
            "child_missing": 3,
            "closure_complete": 0,
        }
        vectors.append(got)
        if got != expected:
            mismatches.append({"index": index, "got": got, "expected": expected})
    trace = json.dumps(vectors, sort_keys=True, separators=(",", ":")).encode()
    return {
        "status": "PASS" if not mismatches else "FAIL",
        "vectors": len(vectors),
        "mismatches": mismatches,
        "trace_sha256": digest_bytes(trace),
        "reference_mode": "SOURCE_EQUATION_BOUNDARY_ONLY",
    }


def integrated_export(target_module: Any, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Export the three existing parent Builds beneath XSCore. / 在 XSCore 下导出现有三个父级 Build。"""

    children: dict[str, Any] = {}
    errors: dict[str, str] = {}
    try:
        frontend = load_exact(CHILD_TARGETS["frontend"], "xscore_frontend")
        children["frontend"] = frontend.FrontendParent(locked_io=False)
        backend = load_exact(CHILD_TARGETS["backend"], "xscore_backend")
        children["backend"] = backend.BackendTop()
        mem = load_exact(CHILD_TARGETS["mem_block"], "xscore_memblock")
        children["mem_block"] = mem.UHSCMemoryMemBlock()
    except Exception as error:
        errors["load"] = repr(error)
    path = WORK / "uhsc-xscore-integrated.sv"
    if errors:
        return {"status": "FAIL", "errors": errors}
    try:
        rtl = target_module.build_verilog(
            {"module": "UHSCXSCoreIntegrated"},
            {**children, "full_port_specs": rows},
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(rtl.encode("utf-8"))
        return {
            "status": "PASS",
            "path": path.relative_to(ROOT).as_posix(),
            "bytes": len(rtl.encode("utf-8")),
            "sha256": digest_bytes(rtl.encode("utf-8")),
            "bound_children": sorted(children),
            "child_missing": 7,
            "semantic_status": "PENDING_CHILD_BEHAVIORAL_CLOSURE",
        }
    except Exception as error:
        return {"status": "FAIL", "errors": {"export": repr(error)}}


def main() -> int:
    """Run all XSCore bounded gates and write evidence. / 运行所有 XSCore 有界门禁并写证据。"""

    WORK.mkdir(parents=True, exist_ok=True)
    rows = inventory_rows()
    target_module = load_exact(TARGET, "v2_xscore_parent_target")
    static = static_audit(TARGET)
    rtl = target_module.build_verilog({"module": "UHSCXSCoreParent"}, {})
    rtl_path = WORK / "uhsc-xscore-parent.sv"
    rtl_path.write_bytes(rtl.encode("utf-8"))
    actual = generated_ports(rtl, "UHSCXSCoreParent")
    expected = {
        str(row["name"]): (str(row.get("direction", "input")), width(row.get("width", 1)))
        for row in rows
    }
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    mismatches = sorted(name for name in set(expected) & set(actual) if expected[name] != actual[name])
    port_pass = not missing and not extra and not mismatches and len(actual) == 308
    direct = direct_probe(target_module)
    differential = differential_probe(target_module)
    integrated = integrated_export(target_module, rows)

    py_compile = subprocess.run(
        [sys.executable, "-m", "py_compile", str(TARGET)],
        capture_output=True, check=False,
    )
    pyright = shutil.which("pyright")
    pyright_result: dict[str, Any]
    if pyright:
        result = subprocess.run([pyright, "--outputjson", str(TARGET)], capture_output=True, check=False)
        pyright_result = {"status": "PASS" if result.returncode == 0 else "FAIL",
                          "returncode": result.returncode,
                          "output_tail": result.stdout.decode("utf-8", "replace")[-1200:]}
    else:
        pyright_result = {"status": "UNAVAILABLE"}

    ver = run_wsl(
        f"verilator --lint-only --Wno-fatal --top-module UHSCXSCoreParent {wsl_path(rtl_path)}"
    )
    yos = run_wsl(
        f"yosys -p 'read_verilog -sv {wsl_path(rtl_path)}; hierarchy -top UHSCXSCoreParent; proc; check'"
    )
    integrated_ver = {"status": "PENDING"}
    integrated_yos = {"status": "PENDING"}
    if integrated.get("status") == "PASS":
        integrated_path = ROOT / str(integrated["path"])
        integrated_ver = run_wsl(
            f"verilator --lint-only --Wno-fatal --top-module UHSCXSCoreIntegrated {wsl_path(integrated_path)}"
        )
        integrated_yos = run_wsl(
            f"yosys -p 'read_verilog -sv {wsl_path(integrated_path)}; hierarchy -top UHSCXSCoreIntegrated; proc; check'"
        )

    port_payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_XSCORE_PARENT_PORT_INVENTORY",
        "source_commit": SOURCE_COMMIT,
        "reference_sha256": REFERENCE_SHA256,
        "module": "XSCore",
        "port_count": 308,
        "inventory_source": "validation/v2-root-port-inventories.json",
        "inventory_sha256": digest(INVENTORY),
        "target": TARGET.relative_to(ROOT).as_posix(),
        "generated_module": "UHSCXSCoreParent",
        "generated_port_count": len(actual),
        "missing": missing,
        "extra": extra,
        "direction_width_mismatches": mismatches,
        "status": "PASS" if port_pass else "FAIL",
    }
    PORT_RESULT.write_text(json.dumps(port_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    contract = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_XSCORE_PARENT_CONTRACT_AUDIT",
        "batch_id": "TOP-XSCORE-CHILD-002",
        "source_commit": SOURCE_COMMIT,
        "source_scala": list(target_module.XSCORE_SOURCE_PATHS),
        "locked_reference": {"sha256": REFERENCE_SHA256, "immutable": True},
        "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(TARGET)},
        "static_audit": static,
        "port_inventory": port_payload,
        "children": {
            name: {
                "target": path.relative_to(ROOT).as_posix(),
                "source": CHILD_SOURCES[name],
                "present": path.is_file(),
                "sha256": digest(path) if path.is_file() else None,
                "closure": "PENDING_CHILD_MISSING",
            }
            for name, path in CHILD_TARGETS.items()
        },
        "status": "PASS_BOUNDED" if static["status"] == "PASS" and port_pass else "FAIL",
        "acceptance_eligible": False,
    }
    CONTRACT_RESULT.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    direct_payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_XSCORE_PARENT_DIRECT",
        "batch_id": "TOP-XSCORE-CHILD-002",
        "direct": direct,
        "py_compile": {"status": "PASS" if py_compile.returncode == 0 else "FAIL"},
        "pyright": pyright_result,
        "status": "PASS_BOUNDED" if direct["status"] == "PASS" and py_compile.returncode == 0 else "FAIL",
        "gates": {"PARENT_CLOSURE_MATCHED": "PENDING_CHILD_MISSING", "ACCEPTED": "NOT_ALLOWED"},
    }
    DIRECT_RESULT.write_text(json.dumps(direct_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    differential_payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_XSCORE_PARENT_DIFFERENTIAL",
        "batch_id": "TOP-XSCORE-CHILD-002",
        "differential": differential,
        "reference": {"mode": "SOURCE_EQUATION_BOUNDARY_ONLY", "locked_xstop_behavioral": "PENDING"},
        "status": differential["status"],
        "gates": {"V2_REFERENCE_MATCHED": "PENDING_LOCKED_XSCORE_CHILD_DIFFERENTIAL",
                  "PARENT_CLOSURE_MATCHED": "PENDING_CHILD_MISSING", "ACCEPTED": "NOT_ALLOWED"},
    }
    DIFF_RESULT.write_text(json.dumps(differential_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    coverage_payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_XSCORE_PARENT_COVERAGE",
        "batch_id": "TOP-XSCORE-CHILD-002",
        "root_module": "XSCore",
        "locked_ports": 308,
        "covered_children": [
            {"name": name, "source": CHILD_SOURCES[name], "target": path.relative_to(ROOT).as_posix(),
             "status": "PRESENT_BOUNDED", "child_missing": 1}
            for name, path in CHILD_TARGETS.items()
        ],
        "bridge_edges": [
            "Frontend.cfVec -> Backend.frontend",
            "Backend.redirect/fence -> Frontend",
            "MemBlock TileLink A/D -> XSCore buffers",
            "XSCore reset/hart/MSI/CLINT fanout",
        ],
        "generated": {"standalone": port_payload, "integrated": integrated,
                      "verilator": ver, "yosys": yos,
                      "integrated_verilator": integrated_ver, "integrated_yosys": integrated_yos},
        "closure": {
            "child_missing": 7,
            "status": "PENDING",
            "reason": "FrontendParent, BackendTop, and UHSCMemoryMemBlock are bounded parent boundaries; no complete child status is asserted.",
        },
        "acceptance_eligible": False,
    }
    COVERAGE_RESULT.write_text(json.dumps(coverage_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    mapping_payload = {
        "schema_version": 1,
        "kind": "V2_XSCORE_PARENT_MAPPING_UPDATE",
        "batch_id": "TOP-XSCORE-CHILD-002",
        "source_commit": SOURCE_COMMIT,
        "entries": [{
            "source_name": "XSCore",
            "local_name": "UHSCXSCoreParent",
            "target": TARGET.relative_to(ROOT).as_posix(),
            "classification": "SOURCE_BACKED_PARENT_BRIDGE",
            "locked_ports": 308,
            "children": ["Frontend", "Backend", "MemBlock"],
            "status": "PASS_BOUNDED_PARENT",
            "closure": "PENDING_CHILD_MISSING",
        }],
        "inventory": "validation/v2-xscore-parent-port-inventory.json",
        "prohibited_claims": ["FULL_XSCORE_CLOSURE", "ACCEPTED"],
    }
    MAPPING_RESULT.write_text(json.dumps(mapping_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    tools_ok = ver["status"] == "PASS" and yos["status"] == "PASS"
    report = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_XSCORE_PARENT",
        "batch_id": "TOP-XSCORE-CHILD-002",
        "target": TARGET.relative_to(ROOT).as_posix(),
        "source_commit": SOURCE_COMMIT,
        "reference_sha256": REFERENCE_SHA256,
        "port_contract": port_payload,
        "static_audit": static,
        "direct": direct_payload,
        "differential": differential_payload,
        "integrated": coverage_payload["generated"],
        "gates": {
            "PY_COMPILE": "PASS" if py_compile.returncode == 0 else "FAIL",
            "PYRIGHT": pyright_result["status"],
            "DIRECT_TEST_PASS_BOUNDED": direct["status"],
            "VERILATOR": ver["status"],
            "YOSYS": yos["status"],
            "PARENT_CLOSURE_MATCHED": "PENDING_CHILD_MISSING",
            "V2_REFERENCE_MATCHED": "PENDING_LOCKED_XSCORE_CHILD_DIFFERENTIAL",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "child_missing": {
            "mask": 7,
            "count": 3,
            "children": ["frontend", "backend", "mem_block"],
            "status": "PENDING",
        },
        "status": "VALIDATOR_PASS_BOUNDED" if static["status"] == "PASS" and port_pass and direct["status"] == "PASS" and tools_ok else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "unclosed": [
            "Frontend/Backend/MemBlock child behavioral closures remain pending.",
            "Locked XSCore differential and complete XSTop hierarchy remain pending.",
            "License review and user approval remain pending.",
        ],
    }
    RESULT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "status": report["status"],
        "ports": len(actual),
        "child_missing": report["child_missing"],
        "verilator": ver["status"],
        "yosys": yos["status"],
        "integrated": integrated.get("status"),
    }, ensure_ascii=False))
    return 0 if report["status"] == "VALIDATOR_PASS_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

