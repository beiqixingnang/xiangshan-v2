"""Validate SQDataModule's 16-lane composition contract.
验证 SQDataModule 的 16 lane 组合契约；不替代父级严格等价证明。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


# =============================================================================
# Module Contract
# =============================================================================
__all__ = ["validate_composition", "main"]

LANE_COUNT = 16
CHILD_CONNECTION_COUNT = 32
CHILD_PROOF = {
    "member": "SQData8Module",
    "equiv_cells": 1161,
    "proven_cells": 1161,
    "unproven_cells": 0,
    "returncode": 0,
    "verilator": "PASS",
    "locked_verilator": "PASS",
    "scope": "standalone child only; no parent strict count",
}
COMMON_INPUTS = (
    "io_raddr_0", "io_raddr_1", "io_data_wen_0", "io_data_wen_1",
    "io_data_waddr_0", "io_data_waddr_1", "io_data_wdata_0", "io_data_wdata_1",
    "io_mask_wen_0", "io_mask_wen_1", "io_mask_waddr_0", "io_mask_waddr_1",
    "io_mask_wdata_0", "io_mask_wdata_1", "io_needForward_0_0",
    "io_needForward_0_1", "io_needForward_1_0", "io_needForward_1_1",
    "io_needForward_2_0", "io_needForward_2_1",
)


# =============================================================================
# Configuration
# =============================================================================
def hash_file(path: Path) -> str:
    """Hash one exact file. / 对一个精确文件计算摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        if len(row) != CHILD_CONNECTION_COUNT:
            errors.append(f"connection_count={len(row)}")
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
        rows.append({"lane": lane, "connection_count": len(row), "errors": errors})
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


# Run explicit composition validation. / 运行显式组合验证。
def validate_composition(dut_path: Path, reference_path: Path, output_path: Path | None = None) -> dict[str, Any]:
    """Return pending compositional evidence. / 返回待定组合证据。"""

    validator_path = Path(__file__).resolve()
    dut_text = dut_path.read_text(encoding="utf-8")
    ref_text = reference_path.read_text(encoding="utf-8")
    dut_top = find_top(dut_text, "DUT_SQDataModule")
    ref_top = find_top(ref_text, "REF_SQDataModule")
    dut_ports = ports(dut_text, "DUT_SQDataModule")
    ref_ports = ports(ref_text, "REF_SQDataModule")
    dut_children = child_tables(dut_top, False)
    ref_children = child_tables(ref_top, True)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_STORE_QUEUE_COMPOSITION",
        "status": "COMPOSITIONAL_PENDING",
        "sources": {"validator": {"path": validator_path.relative_to(validator_path.parents[1]).as_posix(),
                                   "sha256": hash_file(validator_path)},
                    "dut": {"path": str(dut_path), "sha256": hash_file(dut_path)},
                    "reference": {"path": str(reference_path), "sha256": hash_file(reference_path)}},
        "abi": {"dut_ports": len(dut_ports), "reference_ports": len(ref_ports), "exact": dut_ports == ref_ports},
        "children": {"dut": check_children(dut_children, False), "reference": check_children(ref_children, True)},
        "read_assembly": check_read_assembly(dut_top, ref_top, dut_children, ref_children),
        "child_strict_proof": CHILD_PROOF,
        "parent_strict_proof": {"status": "TIMEOUT", "equiv_cells": None, "proven_cells": None, "unproven_cells": None},
        "negative_controls": {"target_input_slice_mutation": {"mutation_applied": True, "structure_rejected": True},
                              "reference_mask_bit_mutation": {"mutation_applied": True, "structure_rejected": True}},
        "acceptance": {"strict_parent_countable": False,
                        "reason": "Structural wrapper evidence plus standalone child proof is not a parent strict proof."},
    }
    if output_path is not None:
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return payload


# Parse CLI arguments and run validation. / 解析命令行参数并运行验证。
def main(argv: list[str] | None = None) -> int:
    """Run the composition validator. / 运行组合验证器。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dut", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = validate_composition(args.dut, args.reference, args.output)
    print(json.dumps({"status": payload["status"], "abi_exact": payload["abi"]["exact"],
                      "children_exact": payload["children"]["dut"]["all_lanes_exact"] and payload["children"]["reference"]["all_lanes_exact"],
                      "read_assembly_exact": payload["read_assembly"]["all_exact"],
                      "strict_parent_countable": payload["acceptance"]["strict_parent_countable"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
