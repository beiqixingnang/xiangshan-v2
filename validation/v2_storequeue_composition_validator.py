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


# Normalize module identity, domain ports, and one verified empty sentinel. / 归一化模块身份、时钟域端口及一个已验证的空哨兵。
def normalized_child_body(text: str, module_pattern: str, clock: str, reset: str) -> str:
    """Return a canonical body after checking all dump-module sentinel uses."""

    match = re.search(module_pattern, text)
    if match is None:
        raise ValueError("expected child module definition is missing")
    header_end = text.find(");", match.start())
    if header_end < 0:
        raise ValueError("child module header is unterminated")
    tail = text[header_end + 2:]
    end_match = re.search(r"(?m)^endmodule\b", tail)
    next_module = re.search(r"(?m)^module\b", tail)
    if end_match is None:
        raise ValueError("child module body is unterminated")
    if next_module is not None and next_module.start() < end_match.start():
        raise ValueError("child module body crossed into a following module")
    body = tail[:end_match.start()]
    body = re.sub(r"\b" + re.escape(clock) + r"\b", "clock", body)
    body = re.sub(r"\b" + re.escape(reset) + r"\b", "reset", body)
    sentinel_prefix = r"\\\$auto\$verilog_backend\.cc:2355:dump_module\$"
    sentinel_occurrences = list(re.finditer(sentinel_prefix + r"(\d+)", body))
    sentinel_declaration = re.compile(
        r"\s*reg\s+" + sentinel_prefix + r"(\d+)\s*=\s*0;\s*")
    sentinel_empty_use = re.compile(
        r"\s*if\s*\(\s*" + sentinel_prefix + r"(\d+)\s*\)\s*begin\s*end\s*")
    declarations: list[re.Match[str]] = []
    uses: list[re.Match[str]] = []
    for line in body.splitlines():
        if "dump_module$" not in line:
            continue
        declaration = sentinel_declaration.fullmatch(line)
        empty_use = sentinel_empty_use.fullmatch(line)
        if declaration is not None:
            declarations.append(declaration)
        elif empty_use is not None:
            uses.append(empty_use)
        else:
            raise ValueError("Yosys dump-module sentinel has a non-empty or unrecognized use")
    if len(declarations) != 1 or len(sentinel_occurrences) != 1 + len(uses):
        raise ValueError("expected one dump-module sentinel declaration and only empty-if uses")
    ordinals = {match.group(1) for match in [*declarations, *uses]}
    if len(ordinals) != 1:
        raise ValueError("Yosys dump-module sentinel ordinal differs within child module")
    body = re.sub(sentinel_prefix + next(iter(ordinals)),
                  r"\\$auto$verilog_backend.cc:2355:dump_module$N", body)
    normalized_declarations: list[str] = []
    statements: list[str] = []
    for line in body.splitlines():
        normalized = line.rstrip()
        if re.match(r"^\s*(input|output|wire|reg)\b", normalized):
            normalized_declarations.append(normalized)
        else:
            statements.append(normalized)
    if not normalized_declarations:
        raise ValueError("child module contains no port or net declarations")
    return "\n".join([*sorted(normalized_declarations), *statements]).strip()


# Verify all embedded target children against the strict leaf target. / 将所有嵌入式目标子模块与严格叶级目标逐一核对。
def check_inline_child_implementations(parent_rtl: str, standalone_rtl: str) -> dict[str, Any]:
    """Require exact child ABI and normalized RTL equality for all target lanes."""

    expected = normalized_child_body(
        standalone_rtl, r"(?m)^module\s+DUT_SQData8Module\s*\(", "clock", "reset")
    standalone_abi = ports(standalone_rtl, "DUT_SQData8Module")
    matches = list(re.finditer(r"(?m)^module\s+\\SQDataModule\.data8_(\d+)\s*\(", parent_rtl))
    lanes = sorted({int(match.group(1)) for match in matches})
    rows: list[dict[str, Any]] = []
    for lane in lanes:
        body = normalized_child_body(
            parent_rtl,
            r"(?m)^module\s+\\SQDataModule\.data8_" + str(lane) + r"\s*\(",
            f"data8_{lane}_sync_clk", f"data8_{lane}_sync_rst")
        inline_abi = ports(parent_rtl, f"\\SQDataModule.data8_{lane}")
        clock_abi = inline_abi.pop(f"data8_{lane}_sync_clk", None)
        reset_abi = inline_abi.pop(f"data8_{lane}_sync_rst", None)
        if clock_abi is not None:
            inline_abi["clock"] = clock_abi
        if reset_abi is not None:
            inline_abi["reset"] = reset_abi
        rows.append({"lane": lane, "abi_exact": inline_abi == standalone_abi,
                     "normalized_body_exact": body == expected,
                     "normalized_body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                     "standalone_body_sha256": hashlib.sha256(expected.encode()).hexdigest(),
                     "first_difference": next((index for index, pair in enumerate(zip(body, expected))
                                                if pair[0] != pair[1]),
                                               None if len(body) == len(expected) else min(len(body), len(expected)))})
    return {"required_lanes": LANE_COUNT, "found_lanes": lanes,
            "all_lanes_match_standalone": lanes == list(range(LANE_COUNT))
            and len(rows) == LANE_COUNT
            and all(row["abi_exact"] and row["normalized_body_exact"] for row in rows),
            "normalization": "module identity plus clock/reset names; declaration order only",
            "lanes": rows}


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
                if direction is None:
                    raise ValueError(f"child port has no direction: {port}")
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


# Normalize generated clock/reset port names for one child instance. / 归一化单个子实例生成的时钟和复位端口名。
def logical_child_ports(table: dict[str, str], lane: int, reference: bool) -> dict[str, str]:
    """Return child ports under their locked logical names."""

    result = dict(table)
    if not reference:
        for logical, generated in (("clock", f"data8_{lane}_sync_clk"),
                                   ("reset", f"data8_{lane}_sync_rst")):
            if generated in result:
                result[logical] = result.pop(generated)
    return result


# Require one simple named input expression before emitting a miter. / 发射 miter 前要求输入表达式为单个简单命名表达式。
def simple_expression(expression: str) -> str:
    """Reject parsed connection expressions outside the checked name/slice form."""

    value = expression.strip()
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*(?:\[\d+(?::\d+)?\])?", value) is None:
        raise ValueError(f"unsupported child connection expression: {expression!r}")
    return value


# Measure a top-level name or constant slice used by one child input. / 计算子输入连接中的顶层名称或常量切片位宽。
def expression_width(expression: str, parent_inputs: dict[str, int]) -> int:
    """Return the exact width of a validated parent input expression."""

    value = simple_expression(expression)
    match = re.fullmatch(
        r"(?P<name>[A-Za-z_][A-Za-z0-9_$]*)(?:\[(?P<high>\d+)(?::(?P<low>\d+))?\])?",
        value)
    if match is None or match.group("name") not in parent_inputs:
        raise ValueError(f"child input does not map to a public parent input: {value}")
    source_width = parent_inputs[match.group("name")]
    high = match.group("high")
    low = match.group("low")
    if high is None:
        return source_width
    high_value = int(high)
    low_value = int(low) if low is not None else high_value
    if low_value > high_value or high_value >= source_width:
        raise ValueError(f"child input slice exceeds parent input width: {value}")
    return high_value - low_value + 1


# Prove that the extracted top has one expected driver per public output. / 确认解析出的顶层每个公开输出恰有一个预期驱动源。
def check_parent_output_drivers(
    top: str,
    parent_ports: dict[str, tuple[str, int]],
    children: dict[int, dict[str, str]],
    reference: bool,
) -> dict[str, int]:
    """Allow one read concatenation assignment or one direct child driver."""

    outputs = {name for name, (direction, _width) in parent_ports.items()
               if direction == "output"}
    direct_counts: dict[str, int] = {name: 0 for name in outputs}
    for lane, row in children.items():
        logical = logical_child_ports(row, lane, reference)
        for port in CHILD_OUTPUTS:
            if port.startswith("io_rdata_"):
                continue
            name = logical.get(port, "").strip()
            if name in outputs:
                direct_counts[name] += 1

    continuous: dict[str, int] = {name: 0 for name in outputs}
    for match in re.finditer(r"(?ms)^\s*assign\s+(.*?)\s*=", top):
        lhs = re.sub(r"\s+", "", match.group(1))
        for output in outputs:
            if re.search(r"\b" + re.escape(output) + r"\b", lhs):
                if lhs != output:
                    raise ValueError(f"unsupported parent output lvalue for {output}: {lhs}")
                continuous[output] += 1

    procedural: dict[str, int] = {name: 0 for name in outputs}
    for raw in top.splitlines():
        line = raw.split("//", 1)[0]
        match = re.match(r"^\s*(?!assign\b)([A-Za-z_]\w*)(?:\[[^]]+\])?\s*(?:<=|=(?!=))", line)
        if match is not None and match.group(1) in outputs:
            procedural[match.group(1)] += 1

    read_outputs = {f"io_rdata_{read}_{kind}"
                    for read in range(2) for kind in ("mask", "data")}
    counts: dict[str, int] = {}
    for name in outputs:
        direct = direct_counts[name]
        assigned = continuous[name]
        procedural_count = procedural[name]
        if name in read_outputs:
            if (direct, assigned, procedural_count) != (0, 1, 0):
                raise ValueError(f"read output has unexpected drivers: {name} "
                                 f"direct={direct}, assign={assigned}, procedural={procedural_count}")
        elif (direct, assigned, procedural_count) != (1, 0, 0):
            raise ValueError(f"forward output has unexpected drivers: {name} "
                             f"direct={direct}, assign={assigned}, procedural={procedural_count}")
        counts[name] = direct + assigned + procedural_count
    return counts


# Build one unrestricted combinational parent composition miter. / 构建一个无约束组合父级组合 miter。
def build_parent_glue_miter(
    dut_parent: str,
    reference_parent: str,
    dut_child: str,
    reference_child: str,
    mutation: tuple[str, int, str, str] | None = None,
) -> str:
    """Compare both parent wiring maps with shared arbitrary leaf outputs."""

    dut_top = find_top(dut_parent, "DUT_SQDataModule")
    ref_top = find_top(reference_parent, "REF_SQDataModule")
    dut_ports = ports(dut_parent, "DUT_SQDataModule")
    ref_ports = ports(reference_parent, "REF_SQDataModule")
    if dut_ports != ref_ports:
        raise ValueError("parent named ABI differs between target and locked reference")
    dut_child_abi = ports(dut_child, "DUT_SQData8Module")
    ref_child_abi = ports(reference_child, "REF_SQData8Module")
    if dut_child_abi != ref_child_abi:
        raise ValueError("standalone child ABI differs between target and locked reference")
    dut_children = child_tables(dut_top, False)
    ref_children = child_tables(ref_top, True)
    if not check_children(dut_children, False)["all_lanes_exact"] \
            or not check_children(ref_children, True)["all_lanes_exact"]:
        raise ValueError("not every lane has the exact 32 named child connections")
    check_parent_output_drivers(dut_top, dut_ports, dut_children, False)
    check_parent_output_drivers(ref_top, ref_ports, ref_children, True)
    assembly = check_read_assembly(dut_top, ref_top, dut_children, ref_children)
    if not assembly["all_exact"]:
        raise ValueError("parent read outputs do not assemble lanes 15 through 0")
    coverage = check_output_coverage(dut_ports, ref_ports, dut_children,
                                     ref_children, assembly)
    if not coverage["all_outputs_covered"]:
        raise ValueError("parent glue does not cover all public outputs")
    inline = check_inline_child_implementations(dut_parent, dut_child)
    if not inline["all_lanes_match_standalone"]:
        raise ValueError("one or more inlined target children differ from the standalone leaf")

    parent_inputs = {name: width for name, (direction, width) in dut_ports.items()
                     if direction == "input"}
    parent_outputs = {name: width for name, (direction, width) in dut_ports.items()
                      if direction == "output"}
    child_inputs = [name for name, (direction, _width) in ref_child_abi.items()
                    if direction == "input"]
    child_input_widths = {name: width for name, (direction, width) in ref_child_abi.items()
                          if direction == "input"}
    child_outputs = {name: width for name, (direction, width) in ref_child_abi.items()
                     if direction == "output"}
    if set(child_inputs) != {"clock", "reset", *COMMON_INPUTS} \
            or set(child_outputs) != set(CHILD_OUTPUTS):
        raise ValueError("standalone leaf port set differs from the audited 32-port composition")
    if mutation is not None:
        if mutation[0] not in {"dut", "reference"} or mutation[1] not in range(LANE_COUNT) \
                or mutation[2] not in child_input_widths:
            raise ValueError("negative-control mutation does not identify one child input mapping")
        if expression_width(mutation[3], parent_inputs) != child_input_widths[mutation[2]]:
            raise ValueError("negative-control mutation changes the child input width")

    lines = ["// StoreQueueData parent wiring miter; child output inputs are shared and arbitrary.",
             "module SQDataModule_GLUE_MITER("]
    declarations = [
        ("input", width, name) for name, width in sorted(parent_inputs.items())
    ]
    declarations.extend(
        ("input", width, f"leaf_l{lane}_{port}")
        for lane in range(LANE_COUNT)
        for port, width in sorted(child_outputs.items())
    )
    declarations.append(("output", 1, "mismatch"))
    for index, (direction, width, name) in enumerate(declarations):
        comma = "," if index + 1 < len(declarations) else ""
        range_text = f" [{width - 1}:0]" if width > 1 else ""
        lines.append(f"  {direction}{range_text} {name}{comma}")
    lines.extend((");", ""))
    for name, width in sorted(parent_outputs.items()):
        range_text = f" [{width - 1}:0]" if width > 1 else ""
        lines.append(f"  wire{range_text} dut_out_{name};")
        lines.append(f"  wire{range_text} ref_out_{name};")

    mismatch_terms: list[str] = []
    mutation_applied = False
    for lane in range(LANE_COUNT):
        dut_row = logical_child_ports(dut_children[lane], lane, False)
        ref_row = logical_child_ports(ref_children[lane], lane, True)
        for port in child_inputs:
            dut_expression = simple_expression(dut_row[port])
            ref_expression = simple_expression(ref_row[port])
            if expression_width(dut_expression, parent_inputs) != child_input_widths[port] \
                    or expression_width(ref_expression, parent_inputs) != child_input_widths[port]:
                raise ValueError(f"child input width mismatch for lane {lane} port {port}")
            if mutation is not None and mutation[1:3] == (lane, port):
                mutation_applied = True
                if mutation[0] == "dut":
                    dut_expression = simple_expression(mutation[3])
                elif mutation[0] == "reference":
                    ref_expression = simple_expression(mutation[3])
                else:
                    raise ValueError(f"unknown mutation side: {mutation[0]}")
            mismatch_terms.append(f"({dut_expression} != {ref_expression})")
        for port in child_outputs:
            if port.startswith("io_rdata_"):
                continue
            dut_public = simple_expression(dut_row[port])
            ref_public = simple_expression(ref_row[port])
            dut_signal = f"leaf_l{lane}_{port}"
            ref_signal = f"leaf_l{lane}_{port}"
            if dut_public not in parent_outputs or ref_public not in parent_outputs:
                raise ValueError(f"child output mapping is not a declared parent output: {port}")
            lines.append(f"  assign dut_out_{dut_public} = {dut_signal};")
            lines.append(f"  assign ref_out_{ref_public} = {ref_signal};")

    if mutation is not None and not mutation_applied:
        raise ValueError("negative-control mutation did not reach a child input mapping")

    for row in assembly["rows"]:
        match = re.fullmatch(r"io_rdata_(\d+)_(mask|data)", row["output"])
        if match is None:
            raise ValueError(f"unexpected read output name: {row['output']}")
        read = int(match.group(1))
        child_port = f"io_rdata_{read}_{'valid' if match.group(2) == 'mask' else 'data'}"
        for side, expression in (("dut", row["dut"]), ("ref", row["reference"])):
            normalized = re.sub(
                r"\bL(\d+)\b",
                lambda found: f"leaf_l{int(found.group(1))}_{child_port}",
                expression,
            )
            if re.search(r"\bL\d+\b", normalized):
                raise ValueError("read assembly names an out-of-range lane")
            lines.append(f"  assign {side}_out_{row['output']} = {normalized};")

    for side in ("dut", "ref"):
        assigned: dict[str, int] = {}
        for match in re.finditer(r"(?m)^\s*assign\s+" + side + r"_out_(\w+)\s*=", "\n".join(lines)):
            name = match.group(1)
            assigned[name] = assigned.get(name, 0) + 1
        if set(assigned) != set(parent_outputs) or any(count != 1 for count in assigned.values()):
            raise ValueError(f"miter does not assign every {side} parent output exactly once")
    mismatch_terms.extend(f"(dut_out_{name} != ref_out_{name})"
                          for name in sorted(parent_outputs))
    lines.append("  assign mismatch = " + " |\n    ".join(mismatch_terms) + ";")
    lines.extend(("endmodule", ""))
    return "\n".join(lines)


# Emit one base glue miter and two-sided formal negative controls. / 生成基准 glue miter 及双侧形式化负控。
def write_parent_glue_miters(
    dut_parent_path: Path,
    reference_parent_path: Path,
    dut_child_path: Path,
    reference_child_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Write unrestricted combinational proof inputs without running a formal tool."""

    output_dir.mkdir(parents=True, exist_ok=True)
    sources = {
        "dut_parent": dut_parent_path.read_text(encoding="utf-8"),
        "reference_parent": reference_parent_path.read_text(encoding="utf-8"),
        "dut_child": dut_child_path.read_text(encoding="utf-8"),
        "reference_child": reference_child_path.read_text(encoding="utf-8"),
    }
    cases = {
        "base": None,
        "target_input_slice_mutation": ("dut", 0, "io_data_wdata_0", "io_data_wdata_0[15:8]"),
        "reference_mask_bit_mutation": ("reference", 0, "io_mask_wdata_0", "io_mask_wdata_0[1]"),
    }
    records: dict[str, Any] = {}
    for name, mutation in cases.items():
        rendered = build_parent_glue_miter(
            sources["dut_parent"], sources["reference_parent"],
            sources["dut_child"], sources["reference_child"], mutation)
        path = output_dir / f"SQDataModule_GLUE_{name}.sv"
        path.write_text(rendered, encoding="utf-8", newline="\n")
        records[name] = {"path": str(path.resolve()), "bytes": path.stat().st_size,
                         "sha256": hash_file(path), "formal_status": "NOT_RUN"}
    return {"top": "SQDataModule_GLUE_MITER", "inputs": records,
            "command_template": "yosys -Q -p 'read_verilog -sv <file>; prep -top SQDataModule_GLUE_MITER; opt; sat -prove mismatch 0'",
            "source_hashes": {name: hashlib.sha256(text.encode()).hexdigest()
                              for name, text in sources.items()},
            "strict_count_eligible": False}


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
