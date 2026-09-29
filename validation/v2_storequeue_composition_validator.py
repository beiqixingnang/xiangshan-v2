"""Validate SQDataModule's 16-lane composition contract.
验证 SQDataModule 的 16 lane 组合契约；不替代父级严格等价证明。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


# =============================================================================
# Module Contract
# =============================================================================
__all__ = ["validate_composition", "main"]

ROOT = Path(__file__).resolve().parents[1]
BUILD_PATH = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Lsqueue.StoreQueueData-Hardware.py"
SCALA_PATH = ROOT / "upstream/src/main/scala/xiangshan/mem/lsqueue/StoreQueueData.scala"
REFERENCE_PARENT_PATH = ROOT / "validation/reference-sv/SQDataModule.sv"
REFERENCE_CHILD_PATH = ROOT / "validation/reference-sv/SQData8Module.sv"
PRIOR_STRICT_EVIDENCE_PATH = ROOT / "validation/v2-build-cpu-memory-lsqueue-storequeuedata-strict-evidence.json"

LANE_COUNT = 16
CHILD_CONNECTION_COUNT = 32
COMMON_INPUTS = (
    "io_raddr_0", "io_raddr_1", "io_data_wen_0", "io_data_wen_1",
    "io_data_waddr_0", "io_data_waddr_1", "io_data_wdata_0", "io_data_wdata_1",
    "io_mask_wen_0", "io_mask_wen_1", "io_mask_waddr_0", "io_mask_waddr_1",
    "io_mask_wdata_0", "io_mask_wdata_1", "io_needForward_0_0",
    "io_needForward_0_1", "io_needForward_1_0", "io_needForward_1_1",
    "io_needForward_2_0", "io_needForward_2_1",
)
CHILD_OUTPUTS = (
    "io_rdata_0_valid", "io_rdata_0_data", "io_rdata_1_valid", "io_rdata_1_data",
    *(f"io_forward{kind}_{forward}" for forward in range(3)
      for kind in ("Valid", "Data")),
)
EXPECTED_CHILD_PORTS = frozenset(("clock", "reset", *COMMON_INPUTS, *CHILD_OUTPUTS))


# =============================================================================
# Configuration
# =============================================================================
def hash_file(path: Path) -> str:
    """Hash one exact file. / 对一个精确文件计算摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


# Describe one exact input artifact. / 描述一个精确输入工件。
def file_record(path: Path) -> dict[str, Any]:
    """Return a path, byte count, and digest for one source file."""

    resolved = path.resolve()
    try:
        display_path = resolved.relative_to(ROOT).as_posix()
    except ValueError:
        display_path = str(resolved)
    return {"path": display_path, "bytes": resolved.stat().st_size,
            "sha256": hash_file(resolved)}


# Rename only the top module in a temporary proof view. / 仅在临时证明视图中重命名顶层模块。
def rename_top_module(text: str, source: str, destination: str) -> str:
    """Rename exactly one top module while preserving all other locked text."""

    pattern = re.compile(r"(?m)^module\s+" + re.escape(source) + r"\s*\(")
    result, count = pattern.subn(f"module {destination}(", text, count=1)
    if count != 1:
        raise ValueError(f"expected one module {source}, found {count}")
    return result


# Import the exact current Build without executing its direct entry. / 精确导入当前 Build 且不执行直接入口。
def load_build(build_path: Path = BUILD_PATH) -> Any:
    """Load the current StoreQueueData Build through its exact file path."""

    module_name = "_v2_storequeue_composition_build"
    spec = importlib.util.spec_from_file_location(module_name, build_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import Build: {build_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


# Export current target variants and make locked reference views. / 导出当前目标特化并建立锁定参考视图。
def prepare_current_artifacts(work_dir: Path | None = None) -> dict[str, Path]:
    """Create current-source RTL views under ignored ``validation/.work``."""

    if work_dir is None:
        work_root = ROOT / "validation/.work/storequeue-composition"
        work_root.mkdir(parents=True, exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix="current-", dir=work_root))
    else:
        work_dir.mkdir(parents=True, exist_ok=False)

    build = load_build()
    artifacts: dict[str, Path] = {}
    for member, prefix in (("SQDataModule", "parent"), ("SQData8Module", "child")):
        dut_text = build.build_verilog({"module": member}, {})
        artifacts[f"dut_{prefix}"] = work_dir / f"DUT_{member}.sv"
        artifacts[f"dut_{prefix}"].write_text(
            rename_top_module(dut_text, member, f"DUT_{member}"),
            encoding="utf-8", newline="\n")
        locked_path = REFERENCE_PARENT_PATH if prefix == "parent" else REFERENCE_CHILD_PATH
        locked_text = locked_path.read_text(encoding="utf-8")
        artifacts[f"reference_{prefix}"] = work_dir / f"REF_{member}.sv"
        artifacts[f"reference_{prefix}"].write_text(
            rename_top_module(locked_text, member, f"REF_{member}"),
            encoding="utf-8", newline="\n")
    return artifacts


# Summarize the last strict attempt without treating stale results as current. / 汇总最近一次严格尝试但不把过期结果当作当前证据。
def prior_strict_attempt(current_build_sha256: str) -> dict[str, Any]:
    """Return historical formal details and whether they bind to today's Build."""

    if not PRIOR_STRICT_EVIDENCE_PATH.is_file():
        return {"status": "MISSING", "path": "validation/v2-build-cpu-memory-lsqueue-storequeuedata-strict-evidence.json"}
    payload = json.loads(PRIOR_STRICT_EVIDENCE_PATH.read_text(encoding="utf-8"))
    recorded_build = payload.get("sources", {}).get("python_build", {}).get("sha256")
    members = payload.get("scope", {}).get("public_variants", [])
    results = payload.get("checks", {}).get("variants", [])
    summaries: dict[str, Any] = {}
    for member, result in zip(members, results):
        proof = result.get("yosys_equiv") or result.get("sat_miter") or {}
        summaries[str(member)] = {
            "status": proof.get("status"),
            "returncode": proof.get("returncode"),
            "timed_out": proof.get("timed_out", False),
            "equiv_cells": proof.get("equiv_cells"),
            "proven_cells": proof.get("proven_cells"),
            "unproven_cells": proof.get("unproven_cells"),
            "output_sha256": proof.get("output_sha256"),
            "output_tail": proof.get("output_tail"),
        }
    fresh = recorded_build == current_build_sha256
    return {
        "status": "CURRENT" if fresh else "STALE",
        "path": file_record(PRIOR_STRICT_EVIDENCE_PATH)["path"],
        "sha256": hash_file(PRIOR_STRICT_EVIDENCE_PATH),
        "recorded_build_sha256": recorded_build,
        "current_build_sha256": current_build_sha256,
        "fresh_for_current_build": fresh,
        "member_results": summaries,
    }


# =============================================================================
# Implementation
# =============================================================================
def find_top(text: str, name: str) -> str:
    """Return one anchored module body. / 返回一个锚定的模块正文。"""

    matches = list(re.finditer(r"(?m)^module\s+" + re.escape(name) + r"\s*\(", text))
    if not matches:
        raise ValueError(f"module not found: {name}")
    start = matches[-1].start()
    end = text.find("\nendmodule", matches[-1].end())
    if end < 0:
        raise ValueError(f"endmodule not found: {name}")
    return text[start:end + len("\nendmodule")]


# Parse one generated or locked port header. / 解析一个生成或锁定的端口头。
def ports(text: str, name: str) -> dict[str, tuple[str, int]]:
    """Return direction and width by public port name. / 按公开端口名返回方向和位宽。"""

    matches = list(re.finditer(r"(?m)^module\s+" + re.escape(name) + r"\s*\((.*?)\)\s*;", text, re.S))
    header = matches[-1] if matches else None
    if header is None:
        raise ValueError(f"header not found: {name}")
    listed = {item.strip() for item in header.group(1).replace("\n", " ").split(",") if item.strip()}
    result: dict[str, tuple[str, int]] = {}
    direction: str | None = None
    width = 1
    # Limit the body scan to this module so a nested child declaration cannot
    # overwrite a grouped parent port width.
    body_end = text.find("\nendmodule", header.end())
    body_text = text[header.end():body_end if body_end >= 0 else len(text)]
    for raw in (header.group(1) + "\n" + body_text).splitlines():
        line = raw.split("//", 1)[0].strip().rstrip(",").rstrip(";").strip()
        if not line:
            continue
        match = re.match(r"^(input|output)\s+(?:\[\s*(\d+)\s*:\s*0\s*\]\s*)?(.+)$", line)
        if match:
            direction = match.group(1)
            width = int(match.group(2)) + 1 if match.group(2) else 1
            names = [item.strip() for item in match.group(3).split(",")]
        elif direction is not None:
            widened = re.match(r"^(?:\[\s*(\d+)\s*:\s*0\s*\]\s*)?(.+)$", line)
            if widened and widened.group(1) is not None:
                width = int(widened.group(1)) + 1
                names = [item.strip() for item in widened.group(2).split(",")]
            else:
                names = [item.strip() for item in line.split(",")]
        else:
            continue
        for port in names:
            if port in listed or not listed or any(
                    re.search(r"\b" + re.escape(port) + r"\b", item)
                    for item in listed):
                result.setdefault(port, (direction, width))
    return result


# Parse child connections from one parent body. / 从一个父正文解析子连接。
def child_tables(text: str, reference: bool) -> dict[int, dict[str, str]]:
    """Return lane-indexed named connections. / 返回按 lane 编号的具名连接。"""

    pattern = (r"(?ms)^\s*SQData8Module\s+data16_(\d+)\s*\((.*?)^\s*\);"
               if reference else
               r"(?ms)^\s*\\SQDataModule\.data8_(\d+)\s+data8_\1\s*\((.*?)^\s*\);")
    result: dict[int, dict[str, str]] = {}
    for index, body in re.findall(pattern, text):
        result[int(index)] = {
            port: expression.strip()
            for port, expression in re.findall(r"\.(\w+)\s*\(\s*([^\n]*?)\s*\)", body)
        }
    return result


# Check child input slices and output lane names. / 检查子输入切片及输出 lane 名称。
def check_children(table: dict[int, dict[str, str]], reference: bool) -> dict[str, Any]:
    """Validate all 16 children and return row evidence. / 验证全部 16 个子模块并返回行证据。"""

    rows: list[dict[str, Any]] = []
    for lane in range(LANE_COUNT):
        row = table.get(lane, {})
        errors: list[str] = []
        logical_ports = set(row)
        if not reference:
            if f"data8_{lane}_sync_clk" in logical_ports:
                logical_ports.remove(f"data8_{lane}_sync_clk")
                logical_ports.add("clock")
            if f"data8_{lane}_sync_rst" in logical_ports:
                logical_ports.remove(f"data8_{lane}_sync_rst")
                logical_ports.add("reset")
        if len(row) != CHILD_CONNECTION_COUNT:
            errors.append(f"connection_count={len(row)}")
        missing_ports = sorted(EXPECTED_CHILD_PORTS - logical_ports)
        unexpected_ports = sorted(logical_ports - EXPECTED_CHILD_PORTS)
        if missing_ports:
            errors.append(f"missing_ports={','.join(missing_ports)}")
        if unexpected_ports:
            errors.append(f"unexpected_ports={','.join(unexpected_ports)}")
        for port in COMMON_INPUTS:
            actual = row.get(port)
            expected = port
            if port in ("io_data_wdata_0", "io_data_wdata_1"):
                expected = f"{port}[{lane * 8 + 7}:{lane * 8}]"
            elif port in ("io_mask_wdata_0", "io_mask_wdata_1"):
                expected = f"{port}[{lane}]"
            if actual != expected:
                errors.append(f"{port}:{actual}!={expected}")
        clock = row.get("clock", row.get(f"data8_{lane}_sync_clk"))
        reset = row.get("reset", row.get(f"data8_{lane}_sync_rst"))
        if clock != "clock":
            errors.append(f"clock:{clock}")
        if reset != "reset":
            errors.append(f"reset:{reset}")
        for forward in range(3):
            valid = row.get(f"io_forwardValid_{forward}")
            data = row.get(f"io_forwardData_{forward}")
            if valid != f"io_forwardMask_{forward}_{lane}":
                errors.append(f"forwardValid_{forward}:{valid}")
            if data != f"io_forwardData_{forward}_{lane}":
                errors.append(f"forwardData_{forward}:{data}")
        for read in range(2):
            for suffix in ("valid", "data"):
                if f"io_rdata_{read}_{suffix}" not in row:
                    errors.append(f"missing_read_output:{read}_{suffix}")
        rows.append({"lane": lane, "connection_count": len(row),
                     "expected_connection_count": CHILD_CONNECTION_COUNT,
                     "named_ports": sorted(row),
                     "logical_port_names": sorted(logical_ports),
                     "port_set_exact": logical_ports == EXPECTED_CHILD_PORTS,
                     "errors": errors})
    return {"lane_count": len(table), "rows": rows,
            "all_lanes_exact": len(table) == LANE_COUNT and all(not row["errors"] for row in rows)}


# Normalize generated child output nets. / 归一化生成的子输出网络名。
def normalize(expression: str, lane_by_net: dict[str, int]) -> str:
    """Replace generated net names with L<n> while preserving order. / 保留顺序并替换生成网络名。"""

    value = re.sub(r"\s+", "", expression)
    for net, lane in sorted(lane_by_net.items(), key=lambda item: -len(item[0])):
        value = value.replace(net, f"L{lane}")
    return value


# Check read mask/data concatenations. / 检查读 mask/data 拼接。
def check_read_assembly(dut: str, ref: str, dut_children: dict[int, dict[str, str]], ref_children: dict[int, dict[str, str]]) -> dict[str, Any]:
    """Require lanes 15 through 0 on both sides. / 要求两侧均为 15 到 0 的 lane 顺序。"""

    expected = "{" + ",".join(f"L{i}" for i in range(15, -1, -1)) + "}"
    rows: list[dict[str, Any]] = []
    for read in range(2):
        for kind, child_port in (("mask", f"io_rdata_{read}_valid"), ("data", f"io_rdata_{read}_data")):
            d_nets = {table[child_port]: lane for lane, table in dut_children.items() if child_port in table}
            r_nets = {table[child_port]: lane for lane, table in ref_children.items() if child_port in table}
            pattern = f"io_rdata_{read}_{kind}"
            d_match = list(re.finditer(r"(?ms)assign\s+" + re.escape(pattern) + r"\s*=\s*(.*?);", dut))
            r_match = list(re.finditer(r"(?ms)assign\s+" + re.escape(pattern) + r"\s*=\s*(.*?);", ref))
            d_value = normalize(d_match[-1].group(1), d_nets) if d_match else ""
            r_value = normalize(r_match[-1].group(1), r_nets) if r_match else ""
            rows.append({"output": pattern, "expected": expected, "dut": d_value, "reference": r_value,
                         "dut_exact": d_value == expected, "reference_exact": r_value == expected})
    return {"rows": rows, "all_exact": all(row["dut_exact"] and row["reference_exact"] for row in rows)}


# Account for every parent output on each implementation side. / 覆盖两侧的每个父级输出。
def check_output_coverage(
    dut_ports: dict[str, tuple[str, int]],
    ref_ports: dict[str, tuple[str, int]],
    dut_children: dict[int, dict[str, str]],
    ref_children: dict[int, dict[str, str]],
    read_assembly: dict[str, Any],
) -> dict[str, Any]:
    """Require reads and every lane-forward result to cover all top outputs."""

    declared = {
        side: {name for name, (direction, _width) in ports_table.items()
               if direction == "output"}
        for side, ports_table in (("dut", dut_ports), ("reference", ref_ports))
    }
    expected_forward = {
        f"io_forward{kind}_{forward}_{lane}"
        for forward in range(3)
        for kind in ("Mask", "Data")
        for lane in range(LANE_COUNT)
    }
    rows: dict[str, Any] = {}
    for side, children in (("dut", dut_children), ("reference", ref_children)):
        mapped_forward: set[str] = set()
        for lane, table in children.items():
            for forward in range(3):
                for kind in ("Valid", "Data"):
                    port = f"io_forward{kind}_{forward}"
                    expression = table.get(port)
                    if expression:
                        mapped_forward.add(expression.strip())
        read_key = "dut_exact" if side == "dut" else "reference_exact"
        covered_reads = {row["output"] for row in read_assembly["rows"]
                         if row[read_key]}
        covered = covered_reads | mapped_forward
        rows[side] = {
            "declared_output_count": len(declared[side]),
            "covered_output_count": len(covered),
            "expected_forward_output_count": len(expected_forward),
            "forward_outputs_complete": expected_forward <= mapped_forward,
            "covered_outputs": sorted(covered),
            "missing_outputs": sorted(declared[side] - covered),
            "unexpected_outputs": sorted(covered - declared[side]),
            "all_outputs_covered": declared[side] == covered,
        }
    return {"dut": rows["dut"], "reference": rows["reference"],
            "all_outputs_covered": rows["dut"]["all_outputs_covered"]
            and rows["reference"]["all_outputs_covered"]}


# Run explicit composition validation. / 运行显式组合验证。
def validate_composition(
    dut_path: Path,
    reference_path: Path,
    output_path: Path | None = None,
    *,
    artifacts: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Return hash-bound structural evidence and explicit pending formal gates."""

    validator_path = Path(__file__).resolve()
    dut_text = dut_path.read_text(encoding="utf-8")
    ref_text = reference_path.read_text(encoding="utf-8")
    dut_top = find_top(dut_text, "DUT_SQDataModule")
    ref_top = find_top(ref_text, "REF_SQDataModule")
    dut_ports = ports(dut_text, "DUT_SQDataModule")
    ref_ports = ports(ref_text, "REF_SQDataModule")
    dut_children = child_tables(dut_top, False)
    ref_children = child_tables(ref_top, True)
    read_assembly = check_read_assembly(dut_top, ref_top, dut_children, ref_children)
    output_coverage = check_output_coverage(
        dut_ports, ref_ports, dut_children, ref_children, read_assembly)
    build_hash = hash_file(BUILD_PATH)
    artifacts = artifacts or {
        "dut_parent": dut_path,
        "reference_parent": reference_path,
    }
    sources = {
        "validator": file_record(validator_path),
        "python_build": file_record(BUILD_PATH),
        "scala": file_record(SCALA_PATH),
        "locked_parent": file_record(REFERENCE_PARENT_PATH),
        "locked_child": file_record(REFERENCE_CHILD_PATH),
        "dut_parent_export": file_record(artifacts["dut_parent"]),
        "reference_parent_view": file_record(artifacts["reference_parent"]),
    }
    for key in ("dut_child", "reference_child"):
        path = artifacts.get(key)
        if path is not None:
            sources[f"{key}_view"] = file_record(path)
    parent_view_hashes = {
        "target_sha256": sources["dut_parent_export"]["sha256"],
        "reference_sha256": sources["reference_parent_view"]["sha256"],
    }
    child_view_hashes = {
        "target_sha256": sources.get("dut_child_view", {}).get("sha256"),
        "reference_sha256": sources.get("reference_child_view", {}).get("sha256"),
    }
    prior_attempt = prior_strict_attempt(build_hash)
    payload: dict[str, Any] = {
        "schema_version": 2,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STORE_QUEUE_COMPOSITION",
        "status": "COMPOSITIONAL_PENDING",
        "sources": sources,
        "abi": {
            "dut_ports": len(dut_ports),
            "reference_ports": len(ref_ports),
            "exact": dut_ports == ref_ports,
            "order_exact": list(dut_ports.items()) == list(ref_ports.items()),
        },
        "children": {"dut": check_children(dut_children, False), "reference": check_children(ref_children, True)},
        "read_assembly": read_assembly,
        "output_coverage": output_coverage,
        "formal_gates": {
            "child_theorem": {
                "status": "NOT_RUN",
                "required": True,
                "member": "SQData8Module",
                "target_sha256": child_view_hashes["target_sha256"],
                "locked_reference_sha256": hash_file(REFERENCE_CHILD_PATH),
                "reference_view_sha256": child_view_hashes["reference_sha256"],
                "result": None,
                "log": None,
            },
            "parent_glue": {
                "status": "NOT_RUN",
                "required": True,
                "target_sha256": parent_view_hashes["target_sha256"],
                "locked_reference_sha256": hash_file(REFERENCE_PARENT_PATH),
                "reference_view_sha256": parent_view_hashes["reference_sha256"],
                "result": None,
                "log": None,
                "coverage_required": {
                    "lanes": LANE_COUNT,
                    "named_child_ports_per_lane": CHILD_CONNECTION_COUNT,
                    "parent_outputs": output_coverage["dut"]["declared_output_count"],
                },
            },
            "negative_controls": {
                "target_side": {"status": "NOT_RUN", "result": None, "log": None},
                "reference_side": {"status": "NOT_RUN", "result": None, "log": None},
                "required_failure_evidence": "explicit SAT counterexample or nonzero final unproven-cell result",
            },
            "strict_count_eligible": False,
            "reason": "This Python-only harness performs structural checks; no current-source formal receipt is attached.",
        },
        "prior_strict_attempt": prior_attempt,
        "acceptance": {"strict_parent_countable": False,
                        "reason": "Current-source child theorem, parent glue proof, and decisive two-sided formal negative controls are missing."},
    }
    if output_path is not None:
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return payload


# Parse CLI arguments and run validation. / 解析命令行参数并运行验证。
def main(argv: list[str] | None = None) -> int:
    """Export current sources, inspect composition, and retain pending evidence."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "validation/v2-storequeue-composition-results.json")
    parser.add_argument("--work-dir", type=Path,
                        help="new ignored work directory; it must not already exist")
    args = parser.parse_args(argv)
    artifacts = prepare_current_artifacts(args.work_dir)
    payload = validate_composition(
        artifacts["dut_parent"], artifacts["reference_parent"], args.output,
        artifacts=artifacts)
    print(json.dumps({"status": payload["status"], "abi_exact": payload["abi"]["exact"],
                      "children_exact": payload["children"]["dut"]["all_lanes_exact"] and payload["children"]["reference"]["all_lanes_exact"],
                      "read_assembly_exact": payload["read_assembly"]["all_exact"],
                      "all_outputs_covered": payload["output_coverage"]["all_outputs_covered"],
                      "formal_gates": {name: gate["status"] for name, gate in payload["formal_gates"].items()
                                       if isinstance(gate, dict) and "status" in gate},
                      "strict_parent_countable": payload["acceptance"]["strict_parent_countable"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
