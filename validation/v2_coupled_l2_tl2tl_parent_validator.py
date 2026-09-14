"""Independent validator for the selected V2 TL2TL CoupledL2 parent.
昆明湖 V2 选定 TL2TL CoupledL2 父级的独立验证器。

The locked DefaultConfig instantiates ``TL2TLCoupledL2``.  This validator
checks that the localized aggregate exposes the exact frozen 540-port
boundary, then exercises bounded A/B/C/D/E, metadata, reset, and backend
paths.  It deliberately records a bounded status: a relay boundary is not a
claim that all nested MSHR/SRAM/prefetch/Diplomacy equations are equivalent.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

from amaranth.sim import Simulator


# =============================================================================
# Module Contract
# =============================================================================
# The validator owns the selected TL2TL parent boundary and never edits the
# immutable Scala source or locked generated reference. / 验证器仅负责选定
# TL2TL 父级边界，绝不修改不可变 Scala 源码或锁定生成参考。


# =============================================================================
# Configuration
# =============================================================================
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Dependency.CoupledL2.Directory-Hardware.py"
SLICE_TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Dependency.CoupledL2.Slice-Hardware.py"
REFERENCE = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
OUT = ROOT / "validation/v2-coupledL2-tl2tl-parent-results.json"
COVERAGE = ROOT / "validation/v2-coupledL2-tl2tl-parent-coverage-manifest.json"
AUDIT = ROOT / "validation/v2-coupledL2-tl2tl-parent-contract-audit.json"
MAPPING = ROOT / "validation/v2-coupledL2-tl2tl-parent-mapping-update.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
SCALA_SOURCES = [
    "upstream/coupledL2/src/main/scala/coupledL2/tl2tl/AcquireUnit.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2tl/Bundle.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2tl/MainPipe.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2tl/MSHR.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2tl/MSHRCtl.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2tl/ProbeQueue.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2tl/RefillUnit.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2tl/SinkB.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2tl/Slice.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2tl/SourceC.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2tl/TL2TLCoupledL2.scala",
]


# =============================================================================
# Implementation
# =============================================================================
# Hash exact bytes without newline normalization. / 计算原始字节摘要且不规范化换行。
def digest(path: Path) -> str:
    """Return a SHA-256 digest. / 返回 SHA-256 摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


# Load the exact hyphenated Build file in an isolated namespace. / 在隔离命名空间加载带连字符的 Build 文件。
def load_target() -> ModuleType:
    """Import the target without sibling Build imports. / 导入目标且不导入同级 Build 文件。"""

    spec = importlib.util.spec_from_file_location("v2_tl2tl_parent_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Load one explicitly selected child for validator-only injection. / 仅为验证器注入显式选定的一个 child。
def load_child(path: Path, name: str) -> ModuleType:
    """Import a child Build file without changing target source imports. / 导入 child Build 文件且不改变目标源导入。"""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load child: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Audit the five-zone, import, and exact adapter contract. / 审计五分区、导入及精确适配器契约。
def static_audit() -> dict[str, Any]:
    """Return machine-readable static evidence. / 返回机器可读静态证据。"""

    raw = TARGET.read_bytes()
    source = raw.decode("utf-8")
    tree = ast.parse(source, filename=str(TARGET))
    zones = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
    positions = [source.find(zone) for zone in zones]
    errors: list[str] = []
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            index = node.lineno - 2
            while index >= 0 and lines[index].strip().startswith("@"):
                index -= 1
            prior = lines[index].strip() if index >= 0 else ""
            if not (prior.startswith("#") and "/" in prior):
                errors.append(f"missing bilingual responsibility comment: {node.name}:{node.lineno}")
    forbidden = {"importlib", "runpy", "subprocess", "socket", "urllib", "pathlib", "os", "sys"}
    forbidden_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            forbidden_imports.extend(item.name for item in node.names if item.name.split(".")[0] in forbidden)
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in forbidden:
            forbidden_imports.append(node.module)
    adapters = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in {"build_verilog", "build_parent_verilog"}]
    signatures = {node.name: [arg.arg for arg in node.args.args] for node in adapters}
    valid = (
        not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw and positions == sorted(positions)
        and all(value >= 0 for value in positions) and not errors and not forbidden_imports
        and signatures.get("build_verilog") == ["configuration", "injected_dependencies"]
        and signatures.get("build_parent_verilog") == ["configuration", "injected_dependencies"]
        and "TL2TLCoupledL2Parent" in source and "tl2tl_parent_port_contract" in source
        and "ACCEPTED" not in source
    )
    return {"status": "PASS" if valid else "FAIL", "path": TARGET.relative_to(ROOT).as_posix(),
            "sha256": digest(TARGET), "bytes": len(raw), "zones": list(zones),
            "adapter_signatures": signatures, "function_comment_errors": errors,
            "forbidden_imports": forbidden_imports}


# Parse a Chisel ANSI module header while inheriting direction/width on
# continuation names. / 解析 Chisel ANSI 模块头，并让续行名称继承方向/位宽。
def parse_header_ports(header: str) -> list[dict[str, Any]]:
    """Return ordered reference port rows. / 返回有序参考端口行。"""

    ports: list[dict[str, Any]] = []
    direction = ""
    width = 1
    for raw_line in header.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line:
            continue
        if line.startswith("module "):
            line = line[line.find("(") + 1 :]
        line = line.rstrip(";)").strip()
        match = re.match(r"^(input|output|inout)\s+(?:\[\s*(\d+)\s*:\s*(\d+)\s*\]\s+)?(.+)$", line)
        if match:
            direction = match.group(1)
            width = int(match.group(2)) - int(match.group(3)) + 1 if match.group(2) else 1
            names = match.group(4)
        else:
            names = line
        for name in names.split(","):
            name = name.strip().strip(")").strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) and direction:
                ports.append({"name": name, "width": width, "direction": direction})
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for port in ports:
        if port["name"] not in seen:
            unique.append(port)
            seen.add(port["name"])
    return unique


# Capture only the immutable TL2TLCoupledL2 header in one streaming pass. /
# 单次流式读取不可变参考，仅截取 TL2TLCoupledL2 头部。
def reference_contract() -> dict[str, Any]:
    """Return the locked parent port contract and selected-top evidence. / 返回锁定父级端口契约及选定顶层证据。"""

    if not REFERENCE.is_file():
        return {"status": "FAIL", "missing": True, "ports": [], "selected_top": False}
    lines: list[str] = []
    active = False
    selected_top = False
    with REFERENCE.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if line.startswith("module TL2TLCoupledL2("):
                active = True
            if active:
                lines.append(line)
                if line.strip() == ");":
                    break
            if "TL2TLCoupledL2" in line and "module" not in line:
                selected_top = selected_top or "TL2TLCoupledL2" in line
    ports = parse_header_ports("".join(lines))
    # The selected module is in the locked XSTop body; this lexical check is
    # intentionally conservative and is supplemented by the exact header.
    if not selected_top:
        try:
            text = REFERENCE.read_text(encoding="utf-8", errors="replace")
            selected_top = bool(re.search(r"TL2TLCoupledL2\s+[^;\n]*\(", text))
        except OSError:
            selected_top = False
    observed_hash = digest(REFERENCE)
    return {"status": "PASS" if len(ports) == 540 and observed_hash == REFERENCE_SHA256 else "FAIL",
            "path": str(REFERENCE), "sha256": observed_hash, "expected_sha256": REFERENCE_SHA256,
            "ports": ports, "port_count": len(ports), "selected_top": selected_top,
            "module": "TL2TLCoupledL2"}


# Extract the generated target's declaration schema. / 提取目标生成 RTL 的声明模式。
def generated_schema(rtl: str, module_name: str) -> dict[str, tuple[str, int]]:
    """Return name→(direction,width) for one generated module. / 返回单个生成模块的名称到（方向、位宽）映射。"""

    start = rtl.index(f"module {module_name}(")
    end = rtl.index("endmodule", start)
    schema: dict[str, tuple[str, int]] = {}
    for line in rtl[start:end].splitlines():
        match = re.match(r"\s*(input|output|inout)(?:\s+\[(\d+):0\])?\s+([^;]+);\s*$", line)
        if match is None:
            continue
        direction, high, names = match.groups()
        width = int(high) + 1 if high is not None else 1
        for name in names.split(","):
            clean = name.strip().replace("\\", "").strip()
            if clean:
                schema[clean] = (direction, width)
    return schema


# Compare the generated aggregate against the locked 540-port envelope. /
# 将生成聚合与锁定的 540 端口包络进行比较。
def contract_differential(module: ModuleType) -> dict[str, Any]:
    """Return strict ordered/name/width contract evidence. / 返回严格有序、名称和位宽契约证据。"""

    reference = reference_contract()
    expected = list(module.tl2tl_parent_port_contract(module.TL2TLCoupledL2ParentConfig()))
    mismatches: list[dict[str, Any]] = []
    if len(expected) != len(reference.get("ports", [])):
        mismatches.append({"index": min(len(expected), len(reference.get("ports", []))),
                           "target_count": len(expected), "reference_count": len(reference.get("ports", []))})
    for index, (target, source) in enumerate(zip(expected, reference.get("ports", []))):
        if target != source:
            mismatches.append({"index": index, "target": target, "reference": source})
    rtl = module.build_parent_verilog({"module": "UHSCTL2TLCoupledL2"}, {})
    actual = generated_schema(rtl, "UHSCTL2TLCoupledL2")
    expected_schema = {row["name"]: (row["direction"], row["width"]) for row in expected}
    schema_missing = sorted(set(expected_schema) - set(actual))
    schema_extra = sorted(set(actual) - set(expected_schema))
    schema_mismatch = sorted(name for name in set(expected_schema) & set(actual) if expected_schema[name] != actual[name])
    return {"status": "PASS" if reference.get("status") == "PASS" and not mismatches and not schema_missing and not schema_extra and not schema_mismatch else "FAIL",
            "target_count": len(expected), "reference_count": len(reference.get("ports", [])), "mismatches": mismatches,
            "generated_count": len(actual), "schema_missing": schema_missing, "schema_extra": schema_extra,
            "schema_direction_width_mismatches": schema_mismatch, "rtl_bytes": len(rtl.encode()),
            "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(), "reference": reference}


# Exercise the bounded relay on all five TileLink channels and metadata. /
# 在所有五个 TileLink 通道及元数据上执行有界中继测试。
def direct_bench(module: ModuleType) -> dict[str, Any]:
    """Run reset, A/D, C, B, E, and metadata transactions. / 运行复位、A/D、C、B、E 和元数据事务。"""

    top = module.TL2TLCoupledL2Parent()
    simulator = Simulator(top)
    simulator.add_clock(1e-6, domain="tl2tl_parent")
    trace: list[dict[str, int]] = []

    async def bench(ctx: Any) -> None:
        for signal in top._inputs:
            ctx.set(signal, 0)
        for bank in range(4):
            ctx.set(getattr(top, f"auto_out_{bank}_a_ready"), 1)
            ctx.set(getattr(top, f"auto_out_{bank}_c_ready"), 1)
            ctx.set(getattr(top, f"auto_out_{bank}_d_valid"), 0)
            ctx.set(getattr(top, f"auto_out_{bank}_b_valid"), 0)
            ctx.set(getattr(top, f"auto_in_{bank}_d_ready"), 1)
            ctx.set(getattr(top, f"auto_in_{bank}_b_ready"), 1)
        ctx.set(top.auto_tpmeta_source_out_ready, 1)
        ctx.set(top.reset, 1)
        await ctx.tick("tl2tl_parent")
        ctx.set(top.reset, 0)
        await ctx.tick("tl2tl_parent")
        if int(ctx.get(top.auto_in_0_a_ready)) != 1:
            raise AssertionError("inner A was not ready after reset")
        # Inner A → outer A (bank 0). / 内侧 A 到外侧 A（bank 0）。
        ctx.set(top.auto_in_0_a_valid, 1)
        ctx.set(top.auto_in_0_a_bits_opcode, 4)
        ctx.set(top.auto_in_0_a_bits_param, 0)
        ctx.set(top.auto_in_0_a_bits_size, 3)
        ctx.set(top.auto_in_0_a_bits_source, 9)
        ctx.set(top.auto_in_0_a_bits_address, 0x12340)
        ctx.set(top.auto_in_0_a_bits_user_reqSource, 3)
        ctx.set(top.auto_in_0_a_bits_data, 0x55AA)
        ctx.set(top.auto_in_0_a_bits_mask, 0xFFFFFFFF)
        await ctx.tick("tl2tl_parent")
        ctx.set(top.auto_in_0_a_valid, 0)
        await ctx.delay(1e-9)
        if not int(ctx.get(top.auto_out_0_a_valid)) or int(ctx.get(top.auto_out_0_a_bits_address)) != 0x12340:
            raise AssertionError("A relay mismatch")
        trace.append({"a_relay": 1, "address": int(ctx.get(top.auto_out_0_a_bits_address))})
        await ctx.tick("tl2tl_parent")
        # Outer D → inner D. / 外侧 D 到内侧 D。
        ctx.set(top.auto_out_0_d_valid, 1)
        ctx.set(top.auto_out_0_d_bits_opcode, 1)
        ctx.set(top.auto_out_0_d_bits_size, 3)
        ctx.set(top.auto_out_0_d_bits_source, 9)
        ctx.set(top.auto_out_0_d_bits_sink, 2)
        ctx.set(top.auto_out_0_d_bits_data, 0xABCDEF)
        await ctx.tick("tl2tl_parent")
        ctx.set(top.auto_out_0_d_valid, 0)
        await ctx.delay(1e-9)
        if not int(ctx.get(top.auto_in_0_d_valid)) or int(ctx.get(top.auto_in_0_d_bits_data)) != 0xABCDEF:
            raise AssertionError("D relay mismatch")
        trace.append({"d_relay": 1, "data": int(ctx.get(top.auto_in_0_d_bits_data))})
        await ctx.tick("tl2tl_parent")
        # Inner C → outer C. / 内侧 C 到外侧 C。
        ctx.set(top.auto_in_0_c_valid, 1)
        ctx.set(top.auto_in_0_c_bits_opcode, 7)
        ctx.set(top.auto_in_0_c_bits_size, 3)
        ctx.set(top.auto_in_0_c_bits_source, 4)
        ctx.set(top.auto_in_0_c_bits_address, 0x4560)
        ctx.set(top.auto_in_0_c_bits_data, 0x77)
        await ctx.tick("tl2tl_parent")
        ctx.set(top.auto_in_0_c_valid, 0)
        await ctx.delay(1e-9)
        if not int(ctx.get(top.auto_out_0_c_valid)) or int(ctx.get(top.auto_out_0_c_bits_opcode)) != 7:
            raise AssertionError("C relay mismatch")
        trace.append({"c_relay": 1, "opcode": int(ctx.get(top.auto_out_0_c_bits_opcode))})
        await ctx.tick("tl2tl_parent")
        # Outer B → inner B. / 外侧 B 到内侧 B。
        ctx.set(top.auto_out_0_b_valid, 1)
        ctx.set(top.auto_out_0_b_bits_opcode, 6)
        ctx.set(top.auto_out_0_b_bits_source, 2)
        ctx.set(top.auto_out_0_b_bits_address, 0x9870)
        await ctx.tick("tl2tl_parent")
        ctx.set(top.auto_out_0_b_valid, 0)
        await ctx.delay(1e-9)
        if not int(ctx.get(top.auto_in_0_b_valid)) or int(ctx.get(top.auto_in_0_b_bits_address)) != 0x9870:
            raise AssertionError("B relay mismatch")
        trace.append({"b_relay": 1, "address": int(ctx.get(top.auto_in_0_b_bits_address))})
        await ctx.tick("tl2tl_parent")
        # E is a direct sink-to-source pass-through at the boundary. / E 通道在边界直接由 sink 透传。
        ctx.set(top.auto_in_0_e_valid, 1)
        ctx.set(top.auto_in_0_e_bits_sink, 5)
        await ctx.delay(1e-9)
        if not int(ctx.get(top.auto_out_0_e_valid)) or int(ctx.get(top.auto_out_0_e_bits_sink)) != 5:
            raise AssertionError("E relay mismatch")
        # Metadata input is held until the output consumer accepts it. / 元数据输入保持到输出消费者接受。
        ctx.set(top.auto_tpmeta_sink_in_valid, 1)
        ctx.set(top.auto_tpmeta_sink_in_bits_hartid, 1)
        ctx.set(top.auto_tpmeta_sink_in_bits_rawData_0, 0x2A)
        await ctx.tick("tl2tl_parent")
        ctx.set(top.auto_tpmeta_sink_in_valid, 0)
        await ctx.delay(1e-9)
        if not int(ctx.get(top.auto_tpmeta_source_out_valid)) or int(ctx.get(top.auto_tpmeta_source_out_bits_rawData_0)) != 0x2A:
            raise AssertionError("TPMeta relay mismatch")
        trace.append({"e_relay": 1, "tpmeta": int(ctx.get(top.auto_tpmeta_source_out_bits_rawData_0))})

    simulator.add_testbench(bench)
    simulator.run()
    canonical = json.dumps(trace, sort_keys=True, separators=(",", ":")).encode()
    return {"status": "PASS", "checks": 6, "trace": trace,
            "trace_sha256": hashlib.sha256(canonical).hexdigest()}


# Elaborate four real slice children through the selected parent boundary. /
# 将四个真实 slice child 通过选定父级边界展开。
def child_integration(module: ModuleType) -> dict[str, Any]:
    """Check injected child hierarchy and parent port preservation. / 检查注入 child 层级并确认父级端口保持。"""

    child_module = load_child(SLICE_TARGET, "v2_tl2tl_parent_slice_child")
    children = [child_module.CoupledL2Slice() for _ in range(4)]
    rtl = module.build_parent_verilog({"module": "UHSCTL2TLCoupledL2"}, {"slices": children})
    parent_schema = generated_schema(rtl, "UHSCTL2TLCoupledL2")
    module_names = sorted(set(re.findall(r"^module\s+([^ (]+)\s*\(", rtl, re.MULTILINE)))
    with tempfile.TemporaryDirectory(prefix="v2_tl2tl_parent_children_") as directory:
        path = Path(directory) / "UHSCTL2TLCoupledL2-children.sv"
        path.write_text(rtl, encoding="utf-8", newline="\n")
        converted = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", check=True).stdout.strip()
        verilator = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                                    f"verilator --lint-only -Wno-fatal --top-module UHSCTL2TLCoupledL2 '{converted}'"],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        yosys = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                                f"yosys -Q -p 'read_verilog -sv {converted}; hierarchy -top UHSCTL2TLCoupledL2; proc; opt; check'"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    expected_count = len(module.tl2tl_parent_port_contract(module.TL2TLCoupledL2ParentConfig()))
    child_modules = [name for name in module_names if "tl2tl_slice_" in name]
    passed = len(parent_schema) == expected_count and len(child_modules) == 4 and verilator.returncode == 0 and yosys.returncode == 0
    return {"status": "PASS" if passed else "FAIL", "parent_ports": len(parent_schema),
            "expected_parent_ports": expected_count, "child_module_count": len(child_modules),
            "modules": module_names, "verilator": "PASS" if verilator.returncode == 0 else "FAIL",
            "yosys": "PASS" if yosys.returncode == 0 else "FAIL", "rtl_bytes": len(rtl.encode()),
            "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(),
            "verilator_returncode": verilator.returncode, "yosys_returncode": yosys.returncode}


# Run Verilator/Yosys on the generated parent. / 对生成父级运行 Verilator/Yosys。
def backend_gates(module: ModuleType) -> dict[str, Any]:
    """Return HDL backend evidence. / 返回 HDL 后端证据。"""

    rtl = module.build_parent_verilog({"module": "UHSCTL2TLCoupledL2"}, {})
    with tempfile.TemporaryDirectory(prefix="v2_tl2tl_parent_") as directory:
        path = Path(directory) / "UHSCTL2TLCoupledL2.sv"
        path.write_text(rtl, encoding="utf-8", newline="\n")
        converted = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", check=True).stdout.strip()
        verilator = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                                    f"verilator --lint-only -Wno-fatal --top-module UHSCTL2TLCoupledL2 '{converted}'"],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        yosys = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                                f"yosys -Q -p 'read_verilog -sv {converted}; hierarchy -top UHSCTL2TLCoupledL2; proc; opt; check'"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return {"verilator": "PASS" if verilator.returncode == 0 else "FAIL",
            "yosys": "PASS" if yosys.returncode == 0 else "FAIL", "rtl_bytes": len(rtl.encode()),
            "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(),
            "verilator_returncode": verilator.returncode, "yosys_returncode": yosys.returncode,
            "verilator_tail": verilator.stderr[-2000:], "yosys_tail": yosys.stderr[-2000:]}


# Hash the selected Scala source inventory. / 计算选定 Scala 源清单摘要。
def source_inventory() -> dict[str, Any]:
    """Return immutable source evidence. / 返回不可变源证据。"""

    entries: list[dict[str, Any]] = []
    missing: list[str] = []
    for relative in SCALA_SOURCES:
        path = ROOT / relative
        if not path.is_file():
            missing.append(relative)
            continue
        entries.append({"path": relative, "sha256": digest(path), "bytes": path.stat().st_size,
                        "lines": len(path.read_text(encoding="utf-8").splitlines())})
    return {"status": "PASS" if not missing else "FAIL", "count": len(entries),
            "missing": missing, "entries": entries}


# Persist all gates without promoting parent or product acceptance. / 持久化全部门禁但不提升父级或产品验收状态。
def main() -> int:
    """Run the validator and write evidence files. / 运行验证器并写入证据文件。"""

    static = static_audit()
    module = load_target()
    compile_result = subprocess.run([sys.executable, "-m", "py_compile", str(TARGET)], capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", check=False)
    if compile_result.returncode:
        raise RuntimeError(compile_result.stderr)
    source = source_inventory()
    contract = contract_differential(module)
    direct = direct_bench(module)
    children = child_integration(module)
    backend = backend_gates(module)
    passed = all((static["status"] == "PASS", source["status"] == "PASS", contract["status"] == "PASS",
                  direct["status"] == "PASS", children["status"] == "PASS",
                  backend["verilator"] == "PASS", backend["yosys"] == "PASS"))
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_COUPLEDL2_TL2TL_PARENT",
        "batch_id": "V2-DEPENDENCY-COUPLEDL2-TL2TL-PARENT-001",
        "source_commit": SOURCE_COMMIT,
        "source_scala_file_count": len(SCALA_SOURCES),
        "target": {"path": static["path"], "sha256": static["sha256"]},
        "static": static, "source_inventory": source, "contract_differential": contract,
        "direct": direct, "child_integration": children, "backend": backend,
        "reference": {"path": str(REFERENCE), "expected_sha256": REFERENCE_SHA256,
                       "observed_sha256": contract["reference"].get("sha256"),
                       "module": "TL2TLCoupledL2", "selected_top": contract["reference"].get("selected_top"),
                       "selection": "LOCKED_XSTOP_DEFAULT_CONFIG"},
        "gates": {
            "PYTHON_PRESENT": static["status"], "DIRECT_TEST_PASS_BOUNDED": direct["status"],
            "V2_REFERENCE_MATCHED": "PASS_BOUNDED_PORT_ENVELOPE_SELECTED_TL2TL" if passed else "FAIL",
            "VERILATOR": backend["verilator"], "YOSYS": backend["yosys"],
            "UHSC_LOCALIZED": "PASS_BOUNDED_TL2TL_PARENT_ADAPTER" if passed else "FAIL",
            "PARENT_CLOSURE_MATCHED": "PENDING_FULL_MSHR_SRAM_PREFETCH_DIPLOMACY_BEHAVIOR",
            "LICENSE_REVIEW": "PENDING_COORDINATOR_REVIEW", "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "VALIDATOR_PASS_BOUNDED" if passed else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "unclosed": [
            "Full TL2TL MSHR/SRAM/Directory/Refill/Prefetch/Diplomacy behavior remains pending.",
            "This batch validates the selected parent port envelope and bounded relay paths only.",
            "Coordinator/license review and user approval remain pending.",
        ],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    COVERAGE.write_text(json.dumps({
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_COUPLEDL2_TL2TL_PARENT_COVERAGE",
        "batch_id": payload["batch_id"], "source_scala_file_count": len(SCALA_SOURCES),
        "reference_port_count": contract["reference_count"], "generated_port_count": contract["generated_count"],
        "contract_status": contract["status"], "direct_checks": direct["checks"],
        "child_integration": children,
        "backend": {"verilator": backend["verilator"], "yosys": backend["yosys"]},
        "covered": ["reset", "inner A to outer A", "outer D to inner D", "inner C to outer C",
                    "outer B to inner B", "E sink relay", "TPMeta one-entry relay"],
        "parent_closure": "PENDING_FULL_CHILD_BEHAVIOR", "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    AUDIT.write_text(json.dumps({
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_COUPLEDL2_TL2TL_PARENT_CONTRACT_AUDIT",
        "batch_id": payload["batch_id"], "static": static["status"], "source_inventory": source["status"],
        "contract_differential": contract["status"], "direct": direct["status"], "child_integration": children["status"], "backend": backend,
        "selected_top": contract["reference"].get("selected_top"),
        "parent_closure": "PENDING_FULL_MSHR_SRAM_PREFETCH_DIPLOMACY_BEHAVIOR",
        "accepted": "NOT_ALLOWED", "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    MAPPING.write_text(json.dumps({
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_COUPLEDL2_TL2TL_PARENT_MAPPING_UPDATE",
        "batch_id": payload["batch_id"], "source_commit": SOURCE_COMMIT,
        "closure_root": "dependency.coupledL2.tl2tl.parent",
        "target_path": static["path"], "source_paths": SCALA_SOURCES,
        "classification": "AGGREGATED_SELECTED_TOP_PARENT_BOUNDARY",
        "reference_module": "TL2TLCoupledL2", "local_name": "UHSCTL2TLCoupledL2",
        "covered_children": ["AcquireUnit", "MainPipe", "MSHR", "MSHRCtl", "ProbeQueue", "RefillUnit", "SinkB", "Slice", "SourceC"],
        "status": payload["status"], "parent_closure": "PENDING_FULL_CHILD_BEHAVIOR", "accepted": "NOT_ALLOWED",
        "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "ports": contract["target_count"],
                      "direct_checks": direct["checks"], "verilator": backend["verilator"],
                      "yosys": backend["yosys"], "accepted": "NOT_ALLOWED"}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
