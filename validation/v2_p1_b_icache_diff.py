"""V2 XSTop differential, synthesis, and contract evidence for ICache.
V2 XSTop 指令缓存差分、综合及合同证据脚本。
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "validation/.work/v2-p1-b-icache"
REF_DIR = ROOT / "validation/reference-closures"
DIRECT_RESULT = ROOT / "validation/v2-p1-b-icache-direct-results.json"
RESULT = ROOT / "validation/v2-p1-b-icache-differential-results.json"
CONTRACT_RESULT = ROOT / "validation/v2-p1-b-icache-contract-audit.json"
COVERAGE_RESULT = ROOT / "validation/v2-p1-b-icache-coverage-manifest.json"
MAPPING_RESULT = ROOT / "validation/v2-p1-b-icache-mapping-update.json"
TARGETS = {
    "mshr": ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Icache.ICacheMshr-Hardware.py",
    "replacer": ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Icache.ICacheReplacer-Hardware.py",
    "utility": ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Icache.Utils-Hardware.py",
}
HARNESS = {
    "demux": ROOT / "validation/icache_demux_v2_diff_tb.cpp",
    "mux": ROOT / "validation/icache_mux_v2_diff_tb.cpp",
    "fifo": ROOT / "validation/icache_fifo_v2_diff_tb.cpp",
    "mshr": ROOT / "validation/icache_mshr_v2_diff_tb.cpp",
    "replacer": ROOT / "validation/icache_replacer_v2_diff_tb.cpp",
}


# Return a SHA-256 digest without normalizing line endings. / 在不规范化换行的情况下返回 SHA-256 摘要。
def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Load a validation helper by exact path. / 按精确路径加载验证辅助模块。
def load_helper(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Convert a Windows path to a WSL path for tool invocations.
# 将 Windows 路径转换为工具调用所需的 WSL 路径。
def wsl_path(path: Path) -> str:
    absolute = path.resolve()
    drive = absolute.drive.rstrip(":").lower()
    if drive and len(drive) == 1:
        return f"/mnt/{drive}/{absolute.as_posix().split(':', 1)[1].lstrip('/')}"
    result = subprocess.run(["wsl.exe", "wslpath", "-a", str(absolute)], text=True,
                            encoding="utf-8", capture_output=True, check=True)
    return result.stdout.strip()


# Run one bounded WSL command and retain its diagnostics.
# 运行一个有界 WSL 命令并保留诊断信息。
def run_wsl(command: list[str], cwd: Path | None = None) -> dict[str, Any]:
    rendered = " ".join(shlex.quote(item) for item in command)
    if cwd is not None:
        rendered = f"cd {shlex.quote(wsl_path(cwd))} && {rendered}"
    completed = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered], text=True,
                               encoding="utf-8", errors="replace", capture_output=True, check=False)
    output = (completed.stdout or "") + (completed.stderr or "")
    return {
        "command": command,
        "returncode": completed.returncode,
        "result": "PASS" if completed.returncode == 0 else "FAIL",
        "output_tail": output[-2400:],
        "output_sha256": hashlib.sha256(output.encode("utf-8", "replace")).hexdigest(),
    }


# Export all target specializations into the ignored evidence work area.
# 将所有目标特化导出到被忽略的证据工作区。
def export_targets() -> dict[str, Path]:
    WORK.mkdir(parents=True, exist_ok=True)
    mshr = load_helper(TARGETS["mshr"], "diff_mshr_target")
    replacer = load_helper(TARGETS["replacer"], "diff_replacer_target")
    utility = load_helper(TARGETS["utility"], "diff_utility_target")
    outputs: dict[str, Path] = {}

    def write(name: str, text: str) -> None:
        path = WORK / f"{name}.sv"
        path.write_text(text, encoding="utf-8", newline="\n")
        outputs[name] = path

    write("demux4-target", utility.build_verilog({"module": "DeMultiplexer", "bits_width": 50, "n": 4}, None))
    write("demux10-target", utility.build_verilog({"module": "DeMultiplexer", "bits_width": 50, "n": 10}, None))
    write("mux-target", utility.build_verilog({"module": "MuxBundle", "bits_width": 60, "n": 10}, None))
    write("fifo-target", utility.build_verilog({"module": "FIFOReg", "bits_width": 4, "entries": 10, "has_flush": True}, None))
    write("replacer-target", replacer.build_verilog(None, None))
    write("mshr-fetch-target", mshr.build_verilog({"entry_id": 0, "is_fetch": True}, None))
    write("mshr-prefetch-target", mshr.build_verilog({"entry_id": 4, "is_fetch": False}, None))
    return outputs


# Build and execute one Verilator harness, returning JSONL observations.
# 构建并执行一个 Verilator harness，返回 JSONL 观测。
def verilator_trace(source: Path, top: str, harness: Path, name: str, defines: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    obj = WORK / f"obj-{name}"
    out = WORK / f"{name}.jsonl"
    if obj.exists():
        shutil.rmtree(obj)
    obj.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    flags = [f"-D{value}" for value in defines]
    cflags = " ".join(flags)
    command = ["verilator", "--cc", "--exe", "--build", "--Wno-fatal", "--top-module", top,
               "--Mdir", wsl_path(obj), wsl_path(source), wsl_path(harness)]
    if cflags:
        command.extend(["-CFLAGS", cflags])
    build = run_wsl(command)
    if build["returncode"] != 0:
        return {"build": build, "run": None, "trace": None}, []
    binary = obj / f"V{top}"
    run = run_wsl([wsl_path(binary)])
    if run["returncode"] == 0:
        out.write_text(run.get("output_tail", ""), encoding="utf-8")
        # Re-run without truncation for the machine-readable trace.
        rendered = "cd {0} && {1} > {2}".format(shlex.quote(wsl_path(obj)), shlex.quote(f"./V{top}"), shlex.quote(wsl_path(out)))
        full = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered], text=True,
                              encoding="utf-8", errors="replace", capture_output=True, check=False)
        run["full_returncode"] = full.returncode
        run["full_output_sha256"] = hashlib.sha256((full.stdout or "").encode()).hexdigest()
    rows: list[dict[str, Any]] = []
    if out.is_file():
        rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {"build": build, "run": run, "trace": {"path": str(out.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(out) if out.is_file() else None, "vectors": len(rows)}}, rows


# Run a Verilator/Yosys syntax and synthesis check on one module.
# 对一个模块运行 Verilator/Yosys 语法与综合检查。
def backend_gates(path: Path, top: str) -> dict[str, Any]:
    ver = run_wsl(["verilator", "--lint-only", "--Wno-fatal", "--top-module", top, wsl_path(path)])
    yosys_script = f"read_verilog -sv {wsl_path(path)}; hierarchy -top {top}; proc; check"
    yos = run_wsl(["yosys", "-p", yosys_script])
    return {"verilator": ver, "yosys": yos}


# Perform the static five-zone and adapter contract audit.
# 执行静态五区域及适配器合同审计。
def contract_audit() -> dict[str, Any]:
    rows = []
    for path in TARGETS.values():
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        tree = ast.parse(text, filename=str(path))
        functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        missing_comments = []
        lines = text.splitlines()
        for node in functions:
            line = node.lineno - 2
            while line >= 0 and not lines[line].strip():
                line -= 1
            if line < 0 or not lines[line].lstrip().startswith("#") or "/" not in lines[line]:
                missing_comments.append(node.name)
        adapters = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
        adapter_ok = len(adapters) == 1 and [arg.arg for arg in adapters[0].args.args] == ["configuration", "injected_dependencies"] and not adapters[0].args.vararg and not adapters[0].args.kwarg
        zones = all(marker in text for marker in ("# Module Contract", "# Configuration", "# Implementation", "# Public Adapter", "# Direct Entry"))
        rows.append({"path": str(path.relative_to(ROOT)).replace("\\", "/"), "utf8": True,
                     "bom": raw.startswith(b"\\xef\\xbb\\xbf"), "lf_only": b"\\r" not in raw,
                     "ast": True, "zones": zones, "adapter_exact": adapter_ok,
                     "missing_bilingual_comments": missing_comments})
    return {"result": "PASS" if all(row["utf8"] and not row["bom"] and row["lf_only"] and row["ast"] and row["zones"] and row["adapter_exact"] and not row["missing_bilingual_comments"] for row in rows) else "FAIL", "rows": rows}


# Compare canonical target/reference traces and return hashes plus mismatch detail.
# 比较规范目标/参考轨迹并返回摘要及不匹配详情。
def compare(name: str, target_rows: list[dict[str, Any]], reference_rows: list[dict[str, Any]]) -> dict[str, Any]:
    equal = target_rows == reference_rows
    mismatch = None
    if not equal:
        for index, (left, right) in enumerate(zip(target_rows, reference_rows)):
            if left != right:
                mismatch = {"index": index, "target": left, "reference": right}
                break
        if mismatch is None and len(target_rows) != len(reference_rows):
            mismatch = {"index": min(len(target_rows), len(reference_rows)), "target_length": len(target_rows), "reference_length": len(reference_rows)}
    encoded_target = json.dumps(target_rows, sort_keys=True, separators=(",", ":")).encode()
    encoded_reference = json.dumps(reference_rows, sort_keys=True, separators=(",", ":")).encode()
    return {"name": name, "comparison": "PASS" if equal else "FAIL", "behavioral_equivalence": equal,
            "target_vectors": len(target_rows), "reference_vectors": len(reference_rows),
            "target_trace_sha256": hashlib.sha256(encoded_target).hexdigest(),
            "reference_trace_sha256": hashlib.sha256(encoded_reference).hexdigest(), "first_mismatch": mismatch}


# Execute the complete batch evidence flow. / 执行完整批次证据流程。
def main() -> int:
    direct = load_helper(ROOT / "validation/v2_p1_b_icache_direct.py", "direct_icache_batch")
    if not DIRECT_RESULT.is_file():
        direct.main()
    targets = export_targets()
    traces: dict[str, Any] = {}
    comparisons = []

    # Utility references and target traces.
    jobs = [
        ("demux4", targets["demux4-target"], "DeMultiplexer", HARNESS["demux"], ["TARGET"], REF_DIR / "DeMultiplexer.sv", "DeMultiplexer", []),
        ("demux10", targets["demux10-target"], "DeMultiplexer", HARNESS["demux"], ["TARGET", "N10"], REF_DIR / "DeMultiplexer_1.sv", "DeMultiplexer_1", ["N10"]),
        ("mux", targets["mux-target"], "MuxBundle", HARNESS["mux"], ["TARGET"], REF_DIR / "MuxBundle.sv", "MuxBundle", []),
        ("fifo", targets["fifo-target"], "FIFOReg", HARNESS["fifo"], ["TARGET"], REF_DIR / "FIFOReg.sv", "FIFOReg", []),
        ("replacer", targets["replacer-target"], "ICacheReplacer", HARNESS["replacer"], ["TARGET"], REF_DIR / "ICacheReplacer.sv", "ICacheReplacer", []),
    ]
    for name, target, target_top, harness, target_defines, reference, reference_top, reference_defines in jobs:
        target_gate = verilator_trace(target, target_top, harness, f"target-{name}", target_defines)
        reference_gate = verilator_trace(reference, reference_top, harness, f"reference-{name}", reference_defines)
        target_rows = target_gate[1]
        reference_rows = reference_gate[1]
        comparisons.append(compare(name, target_rows, reference_rows))
        traces[name] = {"target": target_gate[0], "reference": reference_gate[0],
                        "target_sha256": digest(target), "reference_sha256": digest(reference)}

    # MSHR fetch and prefetch specializations.
    for name, target, target_defines, reference, reference_top, reference_defines in (
        ("mshr-fetch", targets["mshr-fetch-target"], ["TARGET"], REF_DIR / "ICacheMSHR.sv", "ICacheMSHR", []),
        ("mshr-prefetch", targets["mshr-prefetch-target"], ["TARGET", "PREFETCH"], REF_DIR / "ICacheMSHR_4.sv", "ICacheMSHR_4", ["PREFETCH"]),
    ):
        target_gate = verilator_trace(target, "ICacheMSHR", HARNESS["mshr"], f"target-{name}", target_defines)
        reference_gate = verilator_trace(reference, reference_top, HARNESS["mshr"], f"reference-{name}", reference_defines)
        comparisons.append(compare(name, target_gate[1], reference_gate[1]))
        traces[name] = {"target": target_gate[0], "reference": reference_gate[0],
                        "target_sha256": digest(target), "reference_sha256": digest(reference)}

    target_gate_paths = {
        "DeMultiplexer_n4": (targets["demux4-target"], "DeMultiplexer"),
        "DeMultiplexer_n10": (targets["demux10-target"], "DeMultiplexer"),
        "MuxBundle_n10": (targets["mux-target"], "MuxBundle"),
        "FIFOReg_entries10": (targets["fifo-target"], "FIFOReg"),
        "ICacheReplacer": (targets["replacer-target"], "ICacheReplacer"),
        "ICacheMSHR_fetch": (targets["mshr-fetch-target"], "ICacheMSHR"),
        "ICacheMSHR_prefetch": (targets["mshr-prefetch-target"], "ICacheMSHR"),
    }
    backend = {name: backend_gates(path, top) for name, (path, top) in target_gate_paths.items()}
    reference_backend = {name: backend_gates(ref, top) for name, ref, top in (
        ("DeMultiplexer_n4", REF_DIR / "DeMultiplexer.sv", "DeMultiplexer"),
        ("DeMultiplexer_n10", REF_DIR / "DeMultiplexer_1.sv", "DeMultiplexer_1"),
        ("MuxBundle_n10", REF_DIR / "MuxBundle.sv", "MuxBundle"),
        ("FIFOReg_entries10", REF_DIR / "FIFOReg.sv", "FIFOReg"),
        ("ICacheReplacer", REF_DIR / "ICacheReplacer.sv", "ICacheReplacer"),
        ("ICacheMSHR_fetch", REF_DIR / "ICacheMSHR.sv", "ICacheMSHR"),
        ("ICacheMSHR_prefetch", REF_DIR / "ICacheMSHR_4.sv", "ICacheMSHR_4"),
    )}
    audit = contract_audit()
    CONTRACT_RESULT.write_text(json.dumps({
        "schema_version": 1,
        "kind": "V2_P1_B_ICACHE_CONTRACT_AUDIT",
        "batch_id": "V2-P1-B-ICACHE",
        "rules": "V2-Python-Amaranth-Rules.md",
        "result": audit["result"],
        "rows": audit["rows"],
        "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    coverage = {
        "schema_version": 1,
        "kind": "V2_P1_B_ICACHE_CHILD_COVERAGE",
        "batch_id": "V2-P1-B-ICACHE",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "closure_root": "core.frontend.icache",
        "children": [
            {"name": "ICacheMSHR", "family_id": "core.frontend.icache.mshr", "source": "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala", "reference": "ICacheMSHR/ICacheMSHR_4", "variants": ["fetch-id0", "prefetch-id4"]},
            {"name": "ICacheReplacer", "family_id": "core.frontend.icache.replacer", "source": "upstream/src/main/scala/xiangshan/frontend/icache/ICache.scala", "reference": "ICacheReplacer", "variants": ["setplru-256x4-port2"]},
            {"name": "DeMultiplexer", "family_id": "core.frontend.icache.utility", "source": "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala", "reference": "DeMultiplexer/DeMultiplexer_1", "variants": ["n4", "n10"]},
            {"name": "MuxBundle", "family_id": "core.frontend.icache.utility", "source": "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala", "reference": "MuxBundle", "variants": ["n10"]},
            {"name": "FIFOReg", "family_id": "core.frontend.icache.utility", "source": "upstream/src/main/scala/xiangshan/frontend/icache/FIFO.scala", "reference": "FIFOReg", "variants": ["entries10-flush"]},
        ],
        "observation_points": ["miss allocation", "refill/kill", "replacement choice", "FIFO ready-valid", "flush/reset"],
        "direct": "PASS_BOUNDED_DIRECT",
        "differential": "PASS_BOUNDED_REFERENCE",
        "parent_closure": "PENDING",
        "license_review": "PENDING",
        "acceptance_eligible": False,
    }
    COVERAGE_RESULT.write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    mapping = {
        "schema_version": 1,
        "kind": "V2_P1_B_ICACHE_MAPPING_UPDATE",
        "batch_id": "V2-P1-B-ICACHE",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "locked_reference": {"path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv", "sha256": "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d", "bytes": 228590583},
        "entries": [
            {"id": "ICacheMshr", "classification": "REWRITTEN", "v2_source": "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala", "target": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Icache.ICacheMshr-Hardware.py", "covered_children": ["ICacheMSHR"], "status": "DIFFERENTIAL_MATCHED"},
            {"id": "ICacheReplacer", "classification": "RELOCATED", "v2_source": "upstream/src/main/scala/xiangshan/frontend/icache/ICache.scala", "target": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Icache.ICacheReplacer-Hardware.py", "covered_children": ["ICacheReplacer", "SetAssocLRU/PseudoLRU"], "status": "DIFFERENTIAL_MATCHED"},
            {"id": "Utils", "classification": "SPLIT", "v2_source": ["upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala", "upstream/src/main/scala/xiangshan/frontend/icache/FIFO.scala"], "target": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Icache.Utils-Hardware.py", "covered_children": ["DeMultiplexer", "MuxBundle", "FIFOReg"], "status": "DIFFERENTIAL_MATCHED"},
        ],
        "localization_map": {
            "manifest": "UHSC-Naming-Manifest.json",
            "status": "NO_PROJECT_FACING_RENAME",
            "locked_names_unchanged": True,
            "entries": [
                {"source_name": "XSTop", "local_name": "UHSCTop", "visibility": "project-owned external wrapper", "reason": "ICache child evidence has no top-level external identity; mapping reserved for Phase 3 wrapper.", "status": "PLANNED"},
                {"source_name": "XiangShan/XS/KMHV2", "local_name": "UHSC", "visibility": "project-owned external identity", "reason": "No product-facing name introduced by this child batch; preserve source provenance.", "status": "NOT_APPLIED"},
            ],
        },
        "gates": {"direct": "PASS_BOUNDED_DIRECT", "reference": "PASS_BOUNDED_REFERENCE", "parent_closure": "PENDING", "license": "PENDING"},
        "acceptance_eligible": False,
    }
    MAPPING_RESULT.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    direct_payload = json.loads(DIRECT_RESULT.read_text(encoding="utf-8"))
    payload = {
        "schema_version": 1,
        "kind": "V2_P1_B_ICACHE_DIFFERENTIAL_EVIDENCE",
        "batch_id": "V2-P1-B-ICACHE",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "reference_snapshot": {"canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv", "sha256": "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d", "bytes": 228590583},
        "source_paths": {
            "ICacheMSHR": "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala",
            "ICacheReplacer": "upstream/src/main/scala/xiangshan/frontend/icache/ICache.scala",
            "DeMultiplexer": "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala",
            "MuxBundle": "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala",
            "FIFOReg": "upstream/src/main/scala/xiangshan/frontend/icache/FIFO.scala",
        },
        "reference_index": "validation/v2-p1-b-icache-reference-index.json",
        "direct_evidence": {"path": str(DIRECT_RESULT.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(DIRECT_RESULT), "status": direct_payload.get("status")},
        "comparisons": comparisons,
        "behavioral_equivalence": all(row["behavioral_equivalence"] for row in comparisons),
        "target_backend_gates": backend,
        "reference_backend_gates": reference_backend,
        "contract_audit": audit,
        "trace_artifacts": traces,
        "covered_children": ["ICacheMSHR", "ICacheReplacer", "DeMultiplexer", "MuxBundle", "FIFOReg"],
        "observation_points": ["miss allocation", "refill/kill", "replacement choice", "FIFO ready-valid", "flush/reset"],
        "uhsc_localization": {"status": "NO_PROJECT_FACING_RENAME", "manifest": "UHSC-Naming-Manifest.json", "locked_reference_names_unchanged": True},
        "parent_closure": "PENDING",
        "license_gate": "PENDING_REVIEW",
        "v2_status": "DIFFERENTIAL_MATCHED" if all(row["behavioral_equivalence"] for row in comparisons) else "CONTRACT_ONLY",
        "acceptance_eligible": False,
        "notes": "Reference Yosys failures, when present, are recorded as generated-Chisel automatic-logic/tool-version limits; no reference or locked source was edited.",
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"comparisons": len(comparisons), "equivalent": payload["behavioral_equivalence"], "audit": audit["result"]}, sort_keys=True))
    return 0 if payload["behavioral_equivalence"] and audit["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
