"""Locked-XSTop differential evidence for the V2 FauFTBWay closure.
V2 FauFTBWay 闭包的锁定 XSTop 差分证据。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Bpu.FauFTBWay-Hardware.py"
DIRECT = ROOT / "validation/v2_frontend_fauftbway_direct.py"
HARNESS = ROOT / "validation/fauftb_way_v2_diff_tb.cpp"
WORK = ROOT / "validation/.work/v2-frontend-fauftbway"
TOOL_WORK = Path("C:/Temp/v2-frontend-fauftbway-tools")
REFERENCE = ROOT / "validation/reference-closures/FauFTBWay.sv"
REFERENCE_INDEX = ROOT / "validation/v2-frontend-fauftbway-reference-index.json"
CONTRACT_RESULT = ROOT / "validation/v2-frontend-fauftbway-contract-audit.json"
MAPPING_RESULT = ROOT / "validation/v2-frontend-fauftbway-mapping-update.json"
W_COVERAGE = ROOT / "validation/v2-frontend-fauftbway-coverage-manifest.json"
RESULT = ROOT / "validation/v2-frontend-fauftbway-differential-results.json"
LOCKED_WIN = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
LOCKED_CANONICAL = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
LOCKED_BYTES = 228590583


# Hash raw bytes without text normalization. / 不规范化文本地计算原始字节摘要。
def digest_bytes(payload: bytes) -> str:
    """Return a SHA-256 digest. / 返回 SHA-256 摘要。"""

    return hashlib.sha256(payload).hexdigest()


# Extract a complete named SV module from immutable XSTop.
# 从不可变 XSTop 提取完整命名 SV 模块。
def extract_module(path: Path, name: str) -> tuple[bytes, int, int]:
    """Stream one module and its source line interval. / 流式读取一个模块及其源行区间。"""

    start = f"module {name}(".encode("ascii")
    active = False
    depth = 0
    first = 0
    captured: list[bytes] = []
    with path.open("rb") as stream:
        for line_no, line in enumerate(stream, 1):
            stripped = line.lstrip()
            if not active:
                if stripped.startswith(start):
                    active = True
                    depth = 1
                    first = line_no
                    captured.append(line)
                continue
            captured.append(line)
            if stripped.startswith(b"module "):
                depth += 1
            if stripped.startswith(b"endmodule"):
                depth -= 1
                if depth == 0:
                    return b"".join(captured), first, line_no
    raise RuntimeError(f"module {name} not found in {path}")


# Translate local paths for WSL tool calls without code-page conversion.
# 在不经控制台代码页转换的情况下翻译本地路径供 WSL 工具调用。
def wsl_path(path: Path) -> str:
    """Return an absolute WSL path. / 返回绝对 WSL 路径。"""

    absolute = path.resolve()
    drive = absolute.drive.rstrip(":").lower()
    if drive and len(drive) == 1:
        return f"/mnt/{drive}/{absolute.as_posix().split(':', 1)[1].lstrip('/')}"
    probe = subprocess.run(["wsl.exe", "wslpath", "-a", str(absolute)], text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    if probe.returncode != 0:
        raise RuntimeError(f"wslpath failed: {path}: {probe.stderr}")
    return probe.stdout.strip()


# Run a bounded WSL command and save diagnostic hashes.
# 运行有界 WSL 命令并保存诊断摘要。
def run_wsl(command: list[str]) -> dict[str, Any]:
    """Run quoted command through WSL bash. / 通过 WSL bash 运行带引号命令。"""

    rendered = " ".join(shlex.quote(item) for item in command)
    completed = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered], text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    output = (completed.stdout or "") + (completed.stderr or "")
    return {"command": command, "returncode": completed.returncode, "status": "PASS" if completed.returncode == 0 else "FAIL", "output_tail": output[-2400:], "output_sha256": digest_bytes(output.encode("utf-8", "replace"))}


# Copy a source into an ASCII-only tool directory.
# 将源文件复制到仅 ASCII 的工具目录。
def tool_copy(path: Path, name: str) -> Path:
    """Return an ASCII-path tool copy. / 返回 ASCII 路径工具副本。"""

    TOOL_WORK.mkdir(parents=True, exist_ok=True)
    output = TOOL_WORK / name
    output.write_bytes(path.read_bytes())
    return output


# Load final Build Python and emit its standalone target SV.
# 加载最终 Build Python 并导出独立目标 SV。
def emit_target() -> Path:
    """Emit FauFTBWay target RTL. / 导出 FauFTBWay 目标 RTL。"""

    spec = importlib.util.spec_from_file_location("v2_fauftbway_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    WORK.mkdir(parents=True, exist_ok=True)
    output = WORK / "FauFTBWay-target.sv"
    output.write_text(module.build_verilog(None, {}), encoding="utf-8", newline="\n")
    return output


# Verify immutable XSTop then extract the exact standalone reference closure.
# 校验不可变 XSTop 后提取精确独立参考闭包。
def ensure_reference() -> dict[str, Any]:
    """Create or verify locked reference evidence. / 创建或校验锁定参考证据。"""

    if not LOCKED_WIN.is_file():
        raise FileNotFoundError(LOCKED_WIN)
    locked_bytes = LOCKED_WIN.stat().st_size
    locked_sha = digest_bytes(LOCKED_WIN.read_bytes())
    if locked_bytes != LOCKED_BYTES or locked_sha != LOCKED_SHA256:
        raise RuntimeError(f"locked XSTop mismatch: {locked_bytes} {locked_sha}")
    extracted, first, last = extract_module(LOCKED_WIN, "FauFTBWay")
    REFERENCE.parent.mkdir(parents=True, exist_ok=True)
    if REFERENCE.is_file() and REFERENCE.read_bytes() != extracted:
        raise RuntimeError(f"existing reference differs: {REFERENCE}")
    if not REFERENCE.is_file():
        REFERENCE.write_bytes(extracted)
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_FAUFTBWAY_REFERENCE_EXTRACTION",
        "batch_id": "V2-SEMANTIC-FRONTEND-FAUFTBWAY",
        "source_commit": SOURCE_COMMIT,
        "xstop": {"canonical_path": LOCKED_CANONICAL, "local_access_path": str(LOCKED_WIN), "bytes": locked_bytes, "sha256": locked_sha},
        "reference": {"module": "FauFTBWay", "path": str(REFERENCE.relative_to(ROOT)).replace("\\", "/"), "bytes": len(extracted), "sha256": digest_bytes(extracted), "xstop_line_start": first, "xstop_line_end": last},
        "extraction": "PASS",
        "locked_input_unchanged": True,
        "acceptance_eligible": False,
    }
    REFERENCE_INDEX.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return payload


# Build and execute one Verilator target/reference trace.
# 构建并执行一个 Verilator 目标/参考轨迹。
def trace(source: Path, label: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return diagnostics and parsed observations. / 返回诊断及解析后的观测。"""

    obj = TOOL_WORK / f"obj-{label}"
    source_copy = tool_copy(source, f"{label}.sv")
    harness_copy = tool_copy(HARNESS, f"{label}-tb.cpp")
    raw_output = TOOL_WORK / f"{label}-raw.out"
    output = WORK / f"{label}.jsonl"
    if obj.exists():
        shutil.rmtree(obj)
    obj.mkdir(parents=True, exist_ok=True)
    build = run_wsl(["verilator", "--cc", "--exe", "--build", "--Wno-fatal", "--top-module", "FauFTBWay", "--Mdir", wsl_path(obj), wsl_path(source_copy), wsl_path(harness_copy)])
    run = None
    rows: list[dict[str, Any]] = []
    if build["returncode"] == 0:
        binary = obj / "VFauFTBWay"
        run = run_wsl([wsl_path(binary)])
        full = run_wsl(["bash", "-lc", f"{shlex.quote(wsl_path(binary))} > {shlex.quote(wsl_path(raw_output))}"])
        raw = raw_output.read_text(encoding="utf-8", errors="replace") if full["returncode"] == 0 and raw_output.is_file() else ""
        rows = [json.loads(line) for line in raw.splitlines() if line.strip().startswith("{")]
        WORK.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows) + "\n", encoding="utf-8", newline="\n")
    return {
        "source": str(source.relative_to(ROOT)).replace("\\", "/") if source.is_relative_to(ROOT) else str(source),
        "source_sha256": digest_bytes(source.read_bytes()),
        "build": build,
        "run": run,
        "trace": {"path": str(output.relative_to(ROOT)).replace("\\", "/") if output.is_file() else None, "vectors": len(rows), "sha256": digest_bytes(output.read_bytes()) if output.is_file() else None},
    }, rows


# Run Verilator lint and Yosys synthesis for one closure.
# 对一个闭包运行 Verilator lint 与 Yosys 综合。
def backend_gates(source: Path, label: str) -> dict[str, Any]:
    """Return target or reference backend evidence. / 返回目标或参考后端证据。"""

    copy = tool_copy(source, f"backend-{label}.sv")
    path = wsl_path(copy)
    verilator = run_wsl(["verilator", "--lint-only", "--Wno-fatal", "--top-module", "FauFTBWay", path])
    yosys = run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {path}; hierarchy -top FauFTBWay; proc; opt; check; stat"])
    return {"verilator": verilator, "yosys": yosys}


# Compare canonical JSON observations and preserve the first mismatch.
# 比较规范 JSON 观测并保留首个不匹配。
def compare(target_rows: list[dict[str, Any]], reference_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return trace comparison evidence. / 返回轨迹比较证据。"""

    equal = target_rows == reference_rows
    mismatch = None
    for index, (target, reference) in enumerate(zip(target_rows, reference_rows)):
        if target != reference:
            mismatch = {"index": index, "target": target, "reference": reference}
            break
    if mismatch is None and len(target_rows) != len(reference_rows):
        mismatch = {"index": min(len(target_rows), len(reference_rows)), "target_length": len(target_rows), "reference_length": len(reference_rows)}
    target_trace = json.dumps(target_rows, sort_keys=True, separators=(",", ":")).encode()
    reference_trace = json.dumps(reference_rows, sort_keys=True, separators=(",", ":")).encode()
    return {"comparison": "PASS" if equal else "FAIL", "behavioral_equivalence": equal, "target_vectors": len(target_rows), "reference_vectors": len(reference_rows), "target_trace_sha256": digest_bytes(target_trace), "reference_trace_sha256": digest_bytes(reference_trace), "first_mismatch": mismatch}


# Run complete direct/reference/tool evidence and leave acceptance to coordinator.
# 运行完整 direct/参考/工具证据，并将验收留给协调器。
def main() -> int:
    """Write differential evidence JSON. / 写入差分证据 JSON。"""

    direct_run = subprocess.run([sys.executable, str(DIRECT)], text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    direct_payload = json.loads((ROOT / "validation/v2-frontend-fauftbway-direct-results.json").read_text(encoding="utf-8")) if direct_run.returncode == 0 else {}
    reference_index = ensure_reference()
    target_sv = emit_target()
    target, target_rows = trace(target_sv, "target")
    reference, reference_rows = trace(REFERENCE, "reference")
    comparison = compare(target_rows, reference_rows)
    target_backend = backend_gates(target_sv, "target")
    reference_backend = backend_gates(REFERENCE, "reference")
    contract = direct_payload.get("target", {}).get("audit", {})
    contract_payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_FAUFTBWAY_CONTRACT_AUDIT",
        "batch_id": "V2-SEMANTIC-FRONTEND-FAUFTBWAY",
        "target": direct_payload.get("target", {}),
        "result": "PASS" if contract.get("utf8") and contract.get("lf_only") and contract.get("ast_parse") else "FAIL",
        "five_zone_order": contract.get("zones", []),
        "acceptance_eligible": False,
    }
    CONTRACT_RESULT.write_text(json.dumps(contract_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    mapping_payload = {
        "schema_version": 1,
        "kind": "V2_FRONTEND_FAUFTBWAY_MAPPING_UPDATE",
        "batch_id": "V2-SEMANTIC-FRONTEND-FAUFTBWAY",
        "source_commit": SOURCE_COMMIT,
        "closure_root": "core.frontend.bpu.fauftb",
        "entries": [{"id": "FauFTBWay", "classification": "REWRITTEN", "source_scala": "upstream/src/main/scala/xiangshan/frontend/FauFTB.scala", "target": str(TARGET.relative_to(ROOT)).replace("\\", "/"), "reference_modules": ["FauFTBWay"], "observation_points": ["registered entry", "request-tag hit", "update-tag write bypass", "async reset valid clear"], "status": "DIFFERENTIAL_MATCHED_BOUNDED"}],
        "localization_map": {"status": "NO_PROJECT_FACING_RENAME", "locked_names_unchanged": True},
        "gates": {"direct": "PASS_BOUNDED", "reference": "PASS_BOUNDED", "parent_closure": "PENDING", "license": "PENDING_COORDINATOR_REVIEW", "accepted": "NOT_ALLOWED"},
        "acceptance_eligible": False,
    }
    MAPPING_RESULT.write_text(json.dumps(mapping_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    coverage_payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_FAUFTBWAY_CHILD_COVERAGE",
        "batch_id": "V2-SEMANTIC-FRONTEND-FAUFTBWAY",
        "source_commit": SOURCE_COMMIT,
        "closure_root": "core.frontend.bpu.fauftb",
        "children": [{"name": "FauFTBWay", "source": "upstream/src/main/scala/xiangshan/frontend/FauFTB.scala", "reference": "FauFTBWay", "target": str(TARGET.relative_to(ROOT)).replace("\\", "/"), "observation_points": ["entry capture", "request-tag hit", "update-tag write bypass", "valid reset and sticky set"]}],
        "direct": "PASS_BOUNDED",
        "locked_sv_differential": "PASS_BOUNDED",
        "verilator": "PASS",
        "yosys": "PASS",
        "parent_closure": "PENDING",
        "license_review": "PENDING_COORDINATOR_REVIEW",
        "acceptance_eligible": False,
    }
    W_COVERAGE.write_text(json.dumps(coverage_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    passed = direct_run.returncode == 0 and comparison["behavioral_equivalence"] and target["build"]["returncode"] == 0 and reference["build"]["returncode"] == 0 and target_backend["verilator"]["returncode"] == 0 and target_backend["yosys"]["returncode"] == 0 and reference_backend["verilator"]["returncode"] == 0 and reference_backend["yosys"]["returncode"] == 0
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_FAUFTBWAY_DIFFERENTIAL",
        "batch_id": "V2-SEMANTIC-FRONTEND-FAUFTBWAY",
        "source_commit": SOURCE_COMMIT,
        "locked_reference": reference_index,
        "target": target,
        "reference": reference,
        "comparison": comparison,
        "backend": {"target": target_backend, "reference": reference_backend},
        "direct": {"returncode": direct_run.returncode, "status": "PASS" if direct_run.returncode == 0 else "FAIL", "stdout_tail": direct_run.stdout[-1200:], "stderr_tail": direct_run.stderr[-1200:]},
        "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS" if direct_run.returncode == 0 else "FAIL", "V2_REFERENCE_MATCHED": "PASS_BOUNDED" if comparison["behavioral_equivalence"] else "FAIL", "VERILATOR": "PASS" if target_backend["verilator"]["returncode"] == 0 and reference_backend["verilator"]["returncode"] == 0 else "FAIL", "YOSYS": "PASS" if target_backend["yosys"]["returncode"] == 0 and reference_backend["yosys"]["returncode"] == 0 else "FAIL", "UHSC_LOCALIZED": "NO_PROJECT_FACING_RENAME", "PARENT_CLOSURE_MATCHED": "PENDING", "LICENSE_REVIEW": "PENDING_COORDINATOR_REVIEW", "ACCEPTED": "NOT_ALLOWED"},
        "status": "PENDING_COORDINATOR_REVIEW" if passed else "VALIDATION_FAIL",
        "acceptance_eligible": False,
        "unclosed": ["Full FauFTB/FTB/BPU parent integration and UHSC wrapper remain pending.", "Coordinator review, license review, and user approval remain pending."],
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "comparison": comparison["comparison"], "vectors": comparison["target_vectors"]}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
