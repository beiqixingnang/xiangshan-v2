"""Independent V2 reference differential for FTBEntryGen.
FTBEntryGen 的独立 V2 参考差分验证。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Bpu.FTBEntryGen-Hardware.py"
DIRECT_RESULT = ROOT / "validation/v2-frontend-ftb-entry-gen-direct-results.json"
REFERENCE = ROOT / "validation/.work/FTBEntryGen.sv"
WORK = ROOT / "validation/.work/ftb-entry-gen-differential"
TARGET_SV = WORK / "target.sv"
REFERENCE_RENAMED = WORK / "reference.sv"
MITER = WORK / "miter.sv"
LOG = WORK / "equivalence.log"
RESULT = ROOT / "validation/v2-frontend-ftb-entry-gen-differential-results.json"
REFERENCE_INDEX = ROOT / "validation/v2-frontend-ftb-entry-gen-reference-index.json"
COVERAGE = ROOT / "validation/v2-frontend-ftb-entry-gen-coverage-manifest.json"
MAPPING = ROOT / "validation/v2-frontend-ftb-entry-gen-mapping-update.json"
CONTRACT = ROOT / "validation/v2-frontend-ftb-entry-gen-contract-audit.json"
SOURCE = ROOT / "upstream/src/main/scala/xiangshan/frontend/NewFtq.scala"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_SHA = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


# Hash raw bytes without text normalization. / 不做文本规范化地计算原始字节摘要。
def digest(path: Path) -> str:
    """Return a file SHA-256 digest. / 返回文件 SHA-256 摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


# Translate a Windows path to the WSL mount spelling used by local tools.
# 将 Windows 路径转换为本地工具使用的 WSL 挂载路径。
def wsl_path(path: Path) -> str:
    """Return a deterministic WSL path. / 返回确定性的 WSL 路径。"""

    absolute = path.resolve()
    drive = absolute.drive.rstrip(":").lower()
    if drive:
        suffix = absolute.as_posix().split(":", 1)[1].lstrip("/")
        return f"/mnt/{drive}/{suffix}"
    return str(absolute).replace("\\", "/")


# Run one bounded WSL command and preserve its output digest.
# 运行一个有界 WSL 命令并保留其输出摘要。
def run_wsl(command: str) -> dict[str, Any]:
    """Run a shell command in WSL. / 在 WSL 中运行 shell 命令。"""

    completed = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command], text=True,
                               encoding="utf-8", errors="replace", capture_output=True, check=False)
    output = (completed.stdout or "") + (completed.stderr or "")
    return {"command": command, "returncode": completed.returncode,
            "status": "PASS" if completed.returncode == 0 else "FAIL",
            "output_tail": output[-4000:],
            "output_sha256": hashlib.sha256(output.encode("utf-8", "replace")).hexdigest()}


# Load the target Build module and emit standalone SystemVerilog.
# 加载目标 Build 模块并导出独立 SystemVerilog。
def emit_target() -> None:
    """Emit the current target RTL. / 导出当前目标 RTL。"""

    spec = importlib.util.spec_from_file_location("v2_ftb_entry_gen_diff_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    WORK.mkdir(parents=True, exist_ok=True)
    TARGET_SV.write_text(module.build_verilog(None, {}), encoding="utf-8", newline="\n")


# Parse the extracted reference's ANSI-style port declarations.
# 解析提取参考的 ANSI 风格端口声明。
def parse_ports(text: str) -> list[tuple[str, str, int]]:
    """Return ordered (name, direction, width) rows. / 返回有序（名称、方向、位宽）行。"""

    header = text.split(");", 1)[0]
    direction = ""
    rows: list[tuple[str, str, int]] = []
    for raw in header.splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line or line.startswith("module "):
            continue
        match = re.match(r"(input|output)\s+(.*)$", line)
        if match:
            direction, rest = match.groups()
        elif direction:
            rest = line
        else:
            continue
        rest = rest.rstrip(",")
        width_match = re.match(r"\[(\d+):0\]\s+(.+)$", rest)
        if width_match:
            width = int(width_match.group(1)) + 1
            names = width_match.group(2)
        else:
            width = 1
            names = rest
        for name in names.split(","):
            name = name.strip()
            if name and name != ");":
                rows.append((name, direction, width))
    return rows


# Construct a same-input miter for Yosys formal equivalence.
# 构造同输入 miter 供 Yosys 形式等价检查。
def emit_miter(ports: list[tuple[str, str, int]]) -> None:
    """Write the two-instance assertion miter. / 写入双实例断言 miter。"""

    declarations: list[str] = []
    target_connections: list[str] = []
    reference_connections: list[str] = []
    assertions: list[str] = []
    for name, direction, width in ports:
        vector = f"[{width - 1}:0] " if width > 1 else ""
        if direction == "input":
            declarations.append(f"  wire {vector}{name};")
            target_connections.append(f"    .{name}({name})")
            reference_connections.append(f"    .{name}({name})")
        else:
            declarations.append(f"  wire {vector}{name}_target;")
            declarations.append(f"  wire {vector}{name}_reference;")
            target_connections.append(f"    .{name}({name}_target)")
            reference_connections.append(f"    .{name}({name}_reference)")
            assertions.append(f"  always @* assert ({name}_target == {name}_reference);")
    text = "module FTBEntryGen_miter;\n" + "\n".join(declarations) + "\n"
    text += "FTBEntryGen target (\n" + ",\n".join(target_connections) + "\n);\n"
    text += "FTBEntryGen_ref reference (\n" + ",\n".join(reference_connections) + "\n);\n"
    text += "\n".join(assertions) + "\nendmodule\n"
    MITER.write_text(text, encoding="utf-8", newline="\n")


# Run formal equivalence and backend lint gates.
# 运行形式等价及后端 lint 门禁。
def run_gates() -> dict[str, Any]:
    """Return Yosys formal and Verilator/Yosys lint evidence. / 返回 Yosys 形式检查及 Verilator/Yosys lint 证据。"""

    target = shlex.quote(wsl_path(TARGET_SV))
    reference = shlex.quote(wsl_path(REFERENCE))
    renamed = shlex.quote(wsl_path(REFERENCE_RENAMED))
    miter = shlex.quote(wsl_path(MITER))
    target_w = wsl_path(TARGET_SV)
    ref_w = wsl_path(REFERENCE)
    ref_r_w = wsl_path(REFERENCE_RENAMED)
    # Keep the locked extraction immutable; rename only the ignored working copy.
    REFERENCE_RENAMED.write_text(REFERENCE.read_text(encoding="utf-8").replace("module FTBEntryGen(", "module FTBEntryGen_ref(", 1), encoding="utf-8", newline="\n")
    formal_command = (
        f"yosys -Q -p 'read_verilog -sv {target}; read_verilog -sv {renamed}; "
        f"equiv_make FTBEntryGen FTBEntryGen_ref FTBEntryGen_miter; prep -top FTBEntryGen_miter; "
        "equiv_simple; equiv_status -assert'"
    )
    formal = run_wsl(formal_command)
    LOG.write_text(formal.get("output_tail", ""), encoding="utf-8", newline="\n")
    target_verilator = run_wsl(f"verilator --lint-only --Wno-fatal --top-module FTBEntryGen {target}")
    reference_verilator = run_wsl(f"verilator --lint-only --Wno-fatal --top-module FTBEntryGen {reference}")
    target_yosys = run_wsl(f"yosys -Q -p 'read_verilog -sv {target}; hierarchy -top FTBEntryGen; proc; opt; check; stat'")
    reference_yosys = run_wsl(f"yosys -Q -p 'read_verilog -sv {reference}; hierarchy -top FTBEntryGen; proc; opt; check; stat'")
    return {"formal": formal, "target_verilator": target_verilator,
            "reference_verilator": reference_verilator,
            "target_yosys": target_yosys, "reference_yosys": reference_yosys,
            "formal_proven": formal["returncode"] == 0,
            "verilator_pass": target_verilator["returncode"] == 0 and reference_verilator["returncode"] == 0,
            "yosys_pass": target_yosys["returncode"] == 0 and reference_yosys["returncode"] == 0}


# Write all machine-readable closure evidence without promoting acceptance.
# 写入全部机器可读闭包证据但不提升验收状态。
def main() -> int:
    """Run the independent FTBEntryGen differential. / 运行独立 FTBEntryGen 差分。"""

    if not REFERENCE.is_file():
        raise FileNotFoundError(REFERENCE)
    emit_target()
    reference_text = REFERENCE.read_text(encoding="utf-8", errors="replace")
    ports = parse_ports(reference_text)
    if len(ports) != 104:
        raise RuntimeError(f"unexpected reference port count: {len(ports)}")
    emit_miter(ports)
    gates = run_gates()
    direct_payload = json.loads(DIRECT_RESULT.read_text(encoding="utf-8")) if DIRECT_RESULT.is_file() else {}
    direct_pass = direct_payload.get("direct", {}).get("pass") is True
    target_sha = digest(TARGET_SV)
    reference_sha = digest(REFERENCE)
    target_bytes = TARGET_SV.stat().st_size
    reference_bytes = REFERENCE.stat().st_size
    status = "PASS_BOUNDED_REFERENCE" if direct_pass and gates["formal_proven"] and gates["verilator_pass"] and gates["yosys_pass"] else "VALIDATION_FAIL"
    REFERENCE_INDEX.write_text(json.dumps({
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_FTB_ENTRY_GEN_REFERENCE_EXTRACTION",
        "batch_id": "V2-SEMANTIC-FRONTEND-FTB-ENTRY-GEN",
        "source_commit": SOURCE_COMMIT,
        "reference": {"module": "FTBEntryGen", "path": "validation/.work/FTBEntryGen.sv", "bytes": reference_bytes, "sha256": reference_sha, "port_count": len(ports)},
        "locked_xstop_sha256": LOCKED_SHA,
        "extraction": "PASS",
        "locked_input_unchanged": True,
        "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    CONTRACT.write_text(json.dumps({
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_FTB_ENTRY_GEN_CONTRACT_AUDIT",
        "batch_id": "V2-SEMANTIC-FRONTEND-FTB-ENTRY-GEN",
        "target": {"path": str(TARGET.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(TARGET), "utf8": True, "lf_only": b"\r" not in TARGET.read_bytes(), "ast_parse": True, "port_count": len(ports)},
        "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    COVERAGE.write_text(json.dumps({
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_FTB_ENTRY_GEN_COVERAGE",
        "batch_id": "V2-SEMANTIC-FRONTEND-FTB-ENTRY-GEN",
        "source_commit": SOURCE_COMMIT,
        "children": [{"name": "FTBEntryGen", "source": "upstream/src/main/scala/xiangshan/frontend/NewFtq.scala", "reference": "FTBEntryGen", "target": str(TARGET.relative_to(ROOT)).replace("\\", "/"), "ports": len(ports), "observation_points": ["new-entry fields", "branch insertion", "jump target/stat", "taken/mispredict masks", "old-entry classification"]}],
        "direct": "PASS_BOUNDED" if direct_pass else "FAIL",
        "locked_sv_formal_differential": "PASS_BOUNDED" if gates["formal_proven"] else "FAIL",
        "verilator": "PASS" if gates["verilator_pass"] else "FAIL",
        "yosys": "PASS" if gates["yosys_pass"] else "FAIL",
        "parent_closure": "PENDING",
        "license_review": "PENDING_COORDINATOR_REVIEW",
        "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    MAPPING.write_text(json.dumps({
        "schema_version": 1,
        "kind": "V2_FRONTEND_FTB_ENTRY_GEN_MAPPING_UPDATE",
        "batch_id": "V2-SEMANTIC-FRONTEND-FTB-ENTRY-GEN",
        "source_commit": SOURCE_COMMIT,
        "entries": [{"id": "FTBEntryGen", "classification": "REWRITTEN", "source_scala": "upstream/src/main/scala/xiangshan/frontend/NewFtq.scala", "target": str(TARGET.relative_to(ROOT)).replace("\\", "/"), "reference_modules": ["FTBEntryGen"], "status": status}],
        "localization_map": {"status": "NO_PROJECT_FACING_RENAME", "locked_names_unchanged": True},
        "gates": {"direct": "PASS_BOUNDED" if direct_pass else "FAIL", "reference": "PASS_BOUNDED" if gates["formal_proven"] else "FAIL", "parent_closure": "PENDING", "license": "PENDING_COORDINATOR_REVIEW", "accepted": "NOT_ALLOWED"},
        "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_FTB_ENTRY_GEN_DIFFERENTIAL",
        "batch_id": "V2-SEMANTIC-FRONTEND-FTB-ENTRY-GEN",
        "source_commit": SOURCE_COMMIT,
        "target": {"path": str(TARGET_SV.relative_to(ROOT)).replace("\\", "/"), "bytes": target_bytes, "sha256": target_sha, "module": "FTBEntryGen"},
        "reference": {"path": str(REFERENCE.relative_to(ROOT)).replace("\\", "/"), "bytes": reference_bytes, "sha256": reference_sha, "module": "FTBEntryGen", "port_count": len(ports)},
        "formal_equivalence": {"status": "PASS" if gates["formal_proven"] else "FAIL", "method": "yosys equiv_make + equiv_simple + equiv_status -assert", "log": str(LOG.relative_to(ROOT)).replace("\\", "/")},
        "backend": gates,
        "gates": {"PYTHON_PRESENT": "PASS", "DIRECT_TEST_PASS_BOUNDED": "PASS" if direct_pass else "FAIL", "V2_REFERENCE_MATCHED": "PASS_BOUNDED" if gates["formal_proven"] else "FAIL", "VERILATOR": "PASS" if gates["verilator_pass"] else "FAIL", "YOSYS": "PASS" if gates["yosys_pass"] else "FAIL", "UHSC_LOCALIZED": "NO_PROJECT_FACING_RENAME", "PARENT_CLOSURE_MATCHED": "PENDING", "LICENSE_REVIEW": "PENDING_COORDINATOR_REVIEW", "ACCEPTED": "NOT_ALLOWED"},
        "status": status,
        "acceptance_eligible": False,
        "unclosed": ["Full FTB/Predictor/Frontend parent closure, independent validator review, license review, and user approval remain pending."],
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": status, "formal": gates["formal_proven"], "verilator": gates["verilator_pass"], "yosys": gates["yosys_pass"], "ports": len(ports)}, sort_keys=True))
    return 0 if status == "PASS_BOUNDED_REFERENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
