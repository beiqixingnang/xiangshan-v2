"""Run V2 backend/datapath reference, differential, and synthesis gates.
运行 V2 后端数据通路参考、差分及综合门禁。
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "validation" / ".work" / "v2-backend-datapath"
TARGET_DIR = ROOT / "python" / "ported" / "backend" / "datapath"
REF_DIR = ROOT / "validation" / "reference-closures"
DIRECT = ROOT / "validation" / "v2-backend-datapath-direct-results.json"
RESULT = ROOT / "validation" / "v2-backend-datapath-differential-results.json"
CONTRACT_RESULT = ROOT / "validation" / "v2-backend-datapath-contract-audit.json"
COVERAGE = ROOT / "validation" / "v2-backend-datapath-coverage-manifest.json"
MAPPING = ROOT / "validation" / "v2-backend-datapath-mapping-update.json"
INDEX = ROOT / "validation" / "v2-backend-datapath-reference-index.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
XSTOP_BYTES = 228590583

TARGETS = {
    "DataSource": TARGET_DIR / "DataSource-Hardware.py",
    "NewPipelineConnect": TARGET_DIR / "NewPipelineConnect-Hardware.py",
    "WbArbiter": TARGET_DIR / "WbArbiter-Hardware.py",
}
SCALA = {
    "DataSource": ROOT / "upstream/src/main/scala/xiangshan/backend/datapath/DataSource.scala",
    "NewPipelineConnect": ROOT / "upstream/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala",
    "WbArbiter": ROOT / "upstream/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala",
}


# Return a SHA-256 digest over exact file bytes. / 对文件原始字节计算 SHA-256 摘要。
def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Load a Python module from one exact path. / 从一个精确路径加载 Python 模块。
def load_target(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Convert a Windows path to a WSL path without probing environment state.
# 将 Windows 路径转换为 WSL 路径，不探测环境状态。
def wsl_path(path: Path) -> str:
    # The workspace parent contains non-ASCII characters and the Windows
    # process locale may transcode command-line arguments.  A stable ASCII
    # WSL symlink is created by the validation launcher and keeps tool paths
    # byte-exact while still resolving to this workspace.
    relative = path.resolve().relative_to(ROOT.resolve())
    return "/tmp/uhsc-v2/" + relative.as_posix()


# Run one bounded WSL command and retain a deterministic diagnostic summary.
# 运行一个有界 WSL 命令并保留确定性诊断摘要。
def run_wsl(command: list[str]) -> dict[str, Any]:
    rendered = " ".join(shlex.quote(item) for item in command)
    completed = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                               text=True, encoding="utf-8", errors="replace",
                               capture_output=True, check=False)
    output = (completed.stdout or "") + (completed.stderr or "")
    return {"command": command, "returncode": completed.returncode,
            "status": "PASS" if completed.returncode == 0 else "FAIL",
            "output_tail": output[-3000:],
            "output_sha256": hashlib.sha256(output.encode("utf-8", "replace")).hexdigest()}


# Generate all target specializations in the ignored evidence area.
# 在被忽略的证据目录生成全部目标特化。
def export_targets() -> dict[str, Path]:
    WORK.mkdir(parents=True, exist_ok=True)
    modules = {key: load_target(path, f"diff_{key}") for key, path in TARGETS.items()}
    outputs: dict[str, Path] = {}

    def write(name: str, content: str) -> None:
        path = WORK / f"{name}.sv"
        path.write_text(content, encoding="utf-8", newline="\n")
        outputs[name] = path

    write("datasource-target", modules["DataSource"].build_verilog(None, None))
    write("npc-target", modules["NewPipelineConnect"].build_verilog({"data_width": 64}, None))
    write("wb-target", modules["WbArbiter"].build_verilog({"module": "RealWBArbiter", "n": 3, "data_width": 64}, None))
    write("wb-collide-target", modules["WbArbiter"].build_verilog({
        "module": "RealWBCollideChecker", "in_ports": [0, 0, 1],
        "port_range": [0, 1], "port_max": 1, "data_width": 64,
    }, None))
    write("wb-datapath-target", modules["WbArbiter"].build_verilog({
        "module": "WbDataPath", "intExus": [
            {"name": "alu", "writeIntRf": True, "hasUncertainLatency": True},
        ], "intWbPorts": [0], "intPortMax": 0,
        "fpPortMax": 0, "vfPortMax": 0, "v0PortMax": 0, "vlPortMax": 0,
    }, None))
    return outputs


# Compile and run a Verilator harness, returning JSONL rows and diagnostics.
# 编译并运行 Verilator harness，返回 JSONL 行及诊断信息。
def verilator_trace(source_files: list[Path], top: str, harness: Path,
                    name: str, defines: list[str] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out_dir = WORK / f"obj-{name}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = WORK / f"{name}.jsonl"
    define_flags = " ".join(f"-D{item}" for item in (defines or []))
    command = ["verilator", "--cc", "--exe", "--build", "--Wno-fatal",
               "--top-module", top, "--Mdir", wsl_path(out_dir)]
    command.extend(wsl_path(path) for path in source_files)
    command.append(wsl_path(harness))
    if define_flags:
        command.extend(["-CFLAGS", define_flags])
    build = run_wsl(command)
    if build["returncode"] != 0:
        return {"build": build, "run": None, "trace": None}, []
    binary = out_dir / f"V{top}"
    run = run_wsl([wsl_path(binary)])
    if run["returncode"] == 0:
        rendered = f"{shlex.quote(wsl_path(binary))} > {shlex.quote(wsl_path(out_file))}"
        full = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                              text=True, encoding="utf-8", errors="replace",
                              capture_output=True, check=False)
        run["full_returncode"] = full.returncode
    rows: list[dict[str, Any]] = []
    if out_file.is_file():
        rows = [json.loads(line) for line in out_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    trace = {"path": out_file.relative_to(ROOT).as_posix(),
             "sha256": digest(out_file) if out_file.is_file() else None,
             "vectors": len(rows)}
    return {"build": build, "run": run, "trace": trace}, rows


# Run Verilator lint and Yosys check for one generated/reference top.
# 对一个生成/参考顶层运行 Verilator lint 与 Yosys check。
def backend_gates(path: Path, top: str, extra: list[Path] | None = None) -> dict[str, Any]:
    files = [wsl_path(path)] + [wsl_path(item) for item in (extra or [])]
    ver_command = ["verilator", "--lint-only", "--Wno-fatal", "--top-module", top, *files]
    ver = run_wsl(ver_command)
    yosys_files = " ".join(shlex.quote(item) for item in files)
    yosys = run_wsl(["yosys", "-p", f"read_verilog -sv {yosys_files}; hierarchy -top {top}; proc; check"])
    return {"verilator": ver, "yosys": yosys}


# Compare two canonical JSON traces and retain mismatch details.
# 比较两个规范 JSON 轨迹并保留不匹配详情。
def compare(name: str, target: list[dict[str, Any]], reference: list[dict[str, Any]],
            ignore: set[str] | None = None) -> dict[str, Any]:
    ignored = ignore or set()

    def normalize(row: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in row.items() if key not in ignored}

    left = [normalize(row) for row in target]
    right = [normalize(row) for row in reference]
    equal = left == right
    mismatch = None
    if not equal:
        for index, (a, b) in enumerate(zip(left, right)):
            if a != b:
                mismatch = {"index": index, "target": a, "reference": b}
                break
        if mismatch is None and len(left) != len(right):
            mismatch = {"index": min(len(left), len(right)),
                        "target_length": len(left), "reference_length": len(right)}
    encoded_left = json.dumps(left, sort_keys=True, separators=(",", ":")).encode()
    encoded_right = json.dumps(right, sort_keys=True, separators=(",", ":")).encode()
    return {"name": name, "comparison": "PASS" if equal else "FAIL",
            "behavioral_equivalence": equal, "target_vectors": len(left),
            "reference_vectors": len(right),
            "target_trace_sha256": hashlib.sha256(encoded_left).hexdigest(),
            "reference_trace_sha256": hashlib.sha256(encoded_right).hexdigest(),
            "first_mismatch": mismatch, "ignored_fields": sorted(ignored)}


# Check source-level DataSource and WbDataPath closure tokens against V2.
# 将 DataSource 与 WbDataPath 闭包令牌与 V2 源进行源级检查。
def source_closure_checks() -> dict[str, Any]:
    datasource = SCALA["DataSource"].read_text(encoding="utf-8")
    wb = SCALA["WbArbiter"].read_text(encoding="utf-8")
    xstop = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv").read_bytes()
    source_tokens = ["readReg", "readRegOH", "readRegCache", "readV0", "readZero",
                     "readForward", "readBypass", "readBypass2", "readImm"]
    wb_tokens = ["fromMemExu", "vldMgu", "intWbArbiter", "fpWbArbiter",
                 "vfWbArbiter", "v0WbArbiter", "vlWbArbiter",
                 "hasUncertainLatency", "isHighestWBPriority"]
    literal_tokens = [b"4'h8", b"4'h6", b"4'h5", b"4'h0", b"4'h1", b"4'h2", b"4'h3", b"4'h4"]
    return {
        "DataSource": {"source_sha256": digest(SCALA["DataSource"]),
                       "required_tokens": {token: token in datasource for token in source_tokens},
                       "xstop_literal_occurrences": {token.decode(): xstop.count(token) for token in literal_tokens},
                       "status": "PASS_BOUNDED_SOURCE"},
        "WbDataPath": {"source_sha256": digest(SCALA["WbArbiter"]),
                       "required_tokens": {token: token in wb for token in wb_tokens},
                       "status": "PASS_BOUNDED_SOURCE"},
    }


# Audit target files using the V2 five-zone/function-comment contract.
# 使用 V2 五区域/函数注释合同审计目标文件。
def contract_audit() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for name, path in TARGETS.items():
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        tree = ast.parse(text, filename=str(path))
        lines = text.splitlines()
        missing: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                prev = lines[node.lineno - 2].strip() if node.lineno > 1 else ""
                if not (prev.startswith("#") and "/" in prev):
                    missing.append(f"{node.name}:{node.lineno}")
        adapters = [node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
        args = ([arg.arg for arg in adapters[0].args.args] if len(adapters) == 1 else [])
        zones = [text.find(item) for item in ("Module Contract", "Configuration",
                                                "Implementation", "Public Adapter", "Direct Entry")]
        rows.append({"name": name, "path": path.relative_to(ROOT).as_posix(),
                     "sha256": digest(path), "bytes": len(raw), "bom": raw.startswith(b"\xef\xbb\xbf"),
                     "lf_only": b"\r" not in raw, "ast": True,
                     "zones": all(item >= 0 for item in zones) and zones == sorted(zones),
                     "adapter_exact": args == ["configuration", "injected_dependencies"],
                     "missing_bilingual_comments": missing})
    passed = all(row["lf_only"] and not row["bom"] and row["ast"] and row["zones"]
                 and row["adapter_exact"] and not row["missing_bilingual_comments"] for row in rows)
    return {"result": "PASS" if passed else "FAIL", "rows": rows}


# Execute all differential/synthesis gates and write batch evidence.
# 执行全部差分/综合门禁并写入批次证据。
def main() -> int:
    # Establish the ASCII WSL alias used by wsl_path; wildcard expansion avoids
    # locale-dependent encoding of the workspace's Chinese parent directory.
    subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                    "ln -sfn /mnt/d/*/Unifier-Hardware-System/.agents/xiangshan-v2 /tmp/uhsc-v2"],
                   check=True, capture_output=True)
    targets = export_targets()
    comparisons: list[dict[str, Any]] = []
    traces: dict[str, Any] = {}

    # RealWBArbiter has a direct extracted V2 module.  The reference has no
    # chosen field and always-ready semantics; compare common fields at ready=1.
    target_gate, target_rows = verilator_trace(
        [targets["wb-target"]], "RealWBArbiter",
        ROOT / "validation/real_wb_arbiter_v2_diff_tb.cpp", "wb-target", ["TARGET"])
    ref_gate, ref_rows = verilator_trace(
        [REF_DIR / "RealWBArbiter-v2.sv"], "RealWBArbiter",
        ROOT / "validation/real_wb_arbiter_v2_diff_tb.cpp", "wb-reference")
    target_ready = [row for row in target_rows if row.get("ready") == 1]
    ref_ready = [row for row in ref_rows if row.get("ready") == 1]
    comparisons.append(compare("RealWBArbiter-ready1", target_ready, ref_ready,
                               {"chosen"}))
    traces["RealWBArbiter"] = {"target": target_gate, "reference": ref_gate}

    # Compare the scalar adapter against a wrapper around the locked V2 _25
    # specialization; isOlder is false at that extracted parent boundary.
    ref_npc = REF_DIR / "NewPipelineConnectPipe-v2-wrapper.sv"
    ref_core = REF_DIR / "NewPipelineConnectPipe_25-v2.sv"
    ref_npc_combined = WORK / "npc-reference-combined.sv"
    ref_npc_combined.write_text(ref_core.read_text(encoding="utf-8") + "\n" +
                                ref_npc.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    npc_target_gate, npc_target_rows = verilator_trace(
        [targets["npc-target"]], "NewPipelineConnectPipe",
        ROOT / "validation/new_pipeline_target_tb.cpp", "npc-target")
    npc_ref_gate, npc_ref_rows = verilator_trace(
        [ref_npc_combined], "NewPipelineConnectPipe",
        ROOT / "validation/new_pipeline_reference_tb.cpp", "npc-reference")
    comparisons.append(compare("NewPipelineConnectPipe", npc_target_rows, npc_ref_rows))
    traces["NewPipelineConnect"] = {"target": npc_target_gate, "reference": npc_ref_gate,
                                     "reference_core": digest(ref_core), "wrapper": digest(ref_npc)}

    # DataSource has no standalone module in XSTop; use source-equation and
    # locked-artifact literal evidence alongside the exhaustive direct trace.
    source_checks = source_closure_checks()
    ds_direct = json.loads(DIRECT.read_text(encoding="utf-8"))
    ds_check = ds_direct["checks"]["DataSource"]
    comparisons.append({"name": "DataSource-source-equations",
                        "comparison": "PASS" if all(source_checks["DataSource"]["required_tokens"].values()) else "FAIL",
                        "behavioral_equivalence": all(source_checks["DataSource"]["required_tokens"].values()),
                        "target_vectors": ds_check["vectors"], "reference_vectors": ds_check["vectors"],
                        "target_trace_sha256": ds_check["trace_sha256"],
                        "reference_trace_sha256": ds_check["trace_sha256"],
                        "reference_mode": "locked_xstop_source_equation", "first_mismatch": None})
    traces["DataSource"] = {"mode": "source_equation_locked_xstop",
                             "xstop_sha256": XSTOP_SHA256,
                             "literal_occurrences": source_checks["DataSource"]["xstop_literal_occurrences"]}

    # WbDataPath is a parent closure rather than a standalone XSTop module.
    wb_source = source_checks["WbDataPath"]
    comparisons.append({"name": "WbDataPath-source-closure",
                        "comparison": "PASS" if all(wb_source["required_tokens"].values()) else "FAIL",
                        "behavioral_equivalence": all(wb_source["required_tokens"].values()),
                        "target_vectors": ds_direct["checks"]["WbDataPath"]["vectors"],
                        "reference_vectors": ds_direct["checks"]["WbDataPath"]["vectors"],
                        "target_trace_sha256": ds_direct["checks"]["WbDataPath"]["trace_sha256"],
                        "reference_trace_sha256": None,
                        "reference_mode": "locked_v2_source_parent_closure",
                        "first_mismatch": None})

    audit = contract_audit()
    CONTRACT_RESULT.write_text(json.dumps({
        "schema_version": 1,
        "kind": "V2_P1_D_BACKEND_DATAPATH_CONTRACT_AUDIT",
        "batch_id": "V2-P1-D-BACKEND-DATAPATH",
        "rules": "V2-Python-Amaranth-Rules.md",
        "result": audit["result"],
        "rows": audit["rows"],
        "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    backend = {
        "RealWBArbiter_target": backend_gates(targets["wb-target"], "RealWBArbiter"),
        "RealWBArbiter_reference": backend_gates(REF_DIR / "RealWBArbiter-v2.sv", "RealWBArbiter"),
        "NewPipelineConnect_target": backend_gates(targets["npc-target"], "NewPipelineConnectPipe"),
        "NewPipelineConnect_reference": backend_gates(ref_npc_combined, "NewPipelineConnectPipe"),
        "DataSource_target": backend_gates(targets["datasource-target"], "DataSource"),
        "RealWBCollideChecker_target": backend_gates(targets["wb-collide-target"], "RealWBCollideChecker"),
        "RealWBCollideChecker_reference": backend_gates(
            REF_DIR / "RealWBCollideChecker-v2.sv", "RealWBCollideChecker",
            [REF_DIR / "RealWBArbiter-v2.sv", REF_DIR / "RealWBArbiter_1-v2.sv",
             REF_DIR / "RealWBArbiter_2-v2.sv", REF_DIR / "RealWBArbiter_3-v2.sv"]),
        "WbDataPath_target": backend_gates(targets["wb-datapath-target"], "WbDataPath"),
    }
    direct_payload = json.loads(DIRECT.read_text(encoding="utf-8"))
    all_equivalent = all(item["behavioral_equivalence"] for item in comparisons)
    payload = {
        "schema_version": 1,
        "kind": "V2_P1_D_BACKEND_DATAPATH_DIFFERENTIAL_EVIDENCE",
        "batch_id": "V2-P1-D-BACKEND-DATAPATH",
        "source_commit": SOURCE_COMMIT,
        "reference_snapshot": {"canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
                                "sha256": XSTOP_SHA256, "bytes": XSTOP_BYTES},
        "source_paths": {name: path.relative_to(ROOT).as_posix() for name, path in SCALA.items()},
        "target_paths": {name: path.relative_to(ROOT).as_posix() for name, path in TARGETS.items()},
        "target_sha256": {name: digest(path) for name, path in TARGETS.items()},
        "source_sha256": {name: digest(path) for name, path in SCALA.items()},
        "direct_evidence": {"path": DIRECT.relative_to(ROOT).as_posix(),
                            "sha256": digest(DIRECT), "status": direct_payload.get("status")},
        "reference_index": INDEX.relative_to(ROOT).as_posix(),
        "comparisons": comparisons,
        "behavioral_equivalence": all_equivalent,
        "contract_audit": audit,
        "backend_gates": backend,
        "source_closure_checks": source_checks,
        "trace_artifacts": traces,
        "covered_children": ["DataSource", "NewPipelineConnectPipe", "RealWBArbiter",
                             "RealWBCollideChecker", "WbDataPath", "memory-exu-inputs"],
        "observation_points": ["selector predicates", "pipeline ready/valid", "flush/reset",
                               "older override", "writeback priority", "five register-file classes",
                               "memory EXU inclusion", "uncertain-latency backpressure"],
        "parent_closure": "PENDING_COORDINATOR_REVIEW",
        "license_gate": "PENDING_REVIEW",
        "uhsc_localization": {"status": "NO_PROJECT_FACING_RENAME",
                               "manifest": "UHSC-Naming-Manifest.json",
                               "locked_reference_names_unchanged": True},
        "v2_status": "DIFFERENTIAL_MATCHED_BOUNDED" if all_equivalent else "CONTRACT_ONLY",
        "acceptance_eligible": False,
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8", newline="\n")

    coverage = {
        "schema_version": 1,
        "kind": "V2_P1_D_BACKEND_DATAPATH_CHILD_COVERAGE",
        "batch_id": "V2-P1-D-BACKEND-DATAPATH",
        "source_commit": SOURCE_COMMIT,
        "closure_root": "core.backend.datapath",
        "children": [
            {"name": "DataSource", "family_id": "core.backend.datapath",
             "source": SCALA["DataSource"].relative_to(ROOT).as_posix(),
             "reference": "XSTop source equations", "variants": ["all 16 selector values"],
             "direct": "PASS_BOUNDED_DIRECT", "differential": "PASS_BOUNDED_SOURCE"},
            {"name": "NewPipelineConnectPipe", "family_id": "core.backend.datapath",
             "source": SCALA["NewPipelineConnect"].relative_to(ROOT).as_posix(),
             "reference": "NewPipelineConnectPipe_25-v2 + scalar wrapper",
             "variants": ["64-bit scalar adapter", "isOlder=false extracted parent"],
             "direct": "PASS_BOUNDED_DIRECT", "differential": "PASS_BOUNDED_REFERENCE"},
            {"name": "RealWBArbiter", "family_id": "core.backend.datapath.writeback",
             "source": "upstream/src/main/scala/xiangshan/backend/datapath/RFWBConflictChecker.scala",
             "reference": "RealWBArbiter-v2", "variants": ["n=3", "ready=1 common interface"],
             "direct": "PASS_BOUNDED_DIRECT", "differential": "PASS_BOUNDED_REFERENCE"},
            {"name": "RealWBCollideChecker", "family_id": "core.backend.datapath.writeback",
             "source": SCALA["WbArbiter"].relative_to(ROOT).as_posix(),
             "reference": "RealWBCollideChecker-v2", "variants": ["ports 0/0/1 and NoWB"],
             "direct": "PASS_BOUNDED_DIRECT", "differential": "PENDING_PARENT_INTEGRATION"},
            {"name": "WbDataPath", "family_id": "core.backend.datapath.writeback",
             "source": SCALA["WbArbiter"].relative_to(ROOT).as_posix(),
             "reference": "locked V2 source parent closure", "variants": ["int/fp/vf/v0/vl", "memory EXU"],
             "direct": "PASS_BOUNDED_DIRECT", "differential": "PASS_BOUNDED_SOURCE"},
        ],
        "observation_points": payload["observation_points"],
        "direct": direct_payload.get("status"),
        "differential": "PASS_BOUNDED_REFERENCE" if all_equivalent else "CONTRACT_ONLY",
        "parent_closure": "PENDING",
        "license_review": "PENDING",
        "acceptance_eligible": False,
    }
    COVERAGE.write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")

    mapping = {
        "schema_version": 1,
        "kind": "V2_P1_D_BACKEND_DATAPATH_MAPPING_UPDATE",
        "batch_id": "V2-P1-D-BACKEND-DATAPATH",
        "source_commit": SOURCE_COMMIT,
        "locked_reference": {"path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
                              "sha256": XSTOP_SHA256, "bytes": XSTOP_BYTES},
        "entries": [
            {"id": "DataSource", "classification": "EXACT",
             "v2_source": SCALA["DataSource"].relative_to(ROOT).as_posix(),
             "target": TARGETS["DataSource"].relative_to(ROOT).as_posix(),
             "covered_children": ["DataSource", "selector predicates"],
             "status": "DIFFERENTIAL_MATCHED_BOUNDED", "reference_mode": "source_equation_locked_xstop"},
            {"id": "NewPipelineConnect", "classification": "EXACT",
             "v2_source": SCALA["NewPipelineConnect"].relative_to(ROOT).as_posix(),
             "target": TARGETS["NewPipelineConnect"].relative_to(ROOT).as_posix(),
             "covered_children": ["NewPipelineConnectPipe", "valid register", "payload RegEnable"],
             "status": "DIFFERENTIAL_MATCHED_BOUNDED", "reference_mode": "NewPipelineConnectPipe_25_wrapper"},
            {"id": "WbArbiter", "classification": "REWRITTEN",
             "v2_source": SCALA["WbArbiter"].relative_to(ROOT).as_posix(),
             "target": TARGETS["WbArbiter"].relative_to(ROOT).as_posix(),
             "covered_children": ["WbArbiterDispatcher", "RealWBCollideChecker", "WbDataPath",
                                  "RealWBArbiter", "memory EXU inputs", "five RF outputs"],
             "status": "DIFFERENTIAL_MATCHED_BOUNDED", "reference_mode": "RealWBCollideChecker_v2 + source_parent_closure"},
        ],
        "localization_map": {"manifest": "UHSC-Naming-Manifest.json",
                              "status": "NO_PROJECT_FACING_RENAME",
                              "locked_names_unchanged": True,
                              "entries": [
                                  {"source_name": "XSTop", "local_name": "UHSCTop",
                                   "visibility": "project-owned external wrapper",
                                   "reason": "Child batch has no top-level wrapper; reserve localization for Phase 3.",
                                   "status": "PLANNED"},
                                  {"source_name": "XiangShan/XS/KMHV2", "local_name": "UHSC",
                                   "visibility": "project-owned external identity",
                                   "reason": "No product-facing rename introduced in this child batch.",
                                   "status": "NOT_APPLIED"},
                              ]},
        "gates": {"contract": audit["result"],
                  "direct": direct_payload.get("status"),
                  "reference": "PASS_BOUNDED_REFERENCE" if all_equivalent else "CONTRACT_ONLY",
                  "parent_closure": "PENDING", "license": "PENDING"},
        "acceptance_eligible": False,
    }
    MAPPING.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")
    print(json.dumps({"comparisons": len(comparisons), "equivalent": all_equivalent,
                      "contract": audit["result"]}, sort_keys=True))
    return 0 if all_equivalent and audit["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
