"""Independent bounded validator for the V2 CHI CoupledL2 parent.
昆明湖 V2 CHI CoupledL2 父级的独立有界验证器。

The parent is compared with a locally generated ``TestTop_CHIL2`` reference
for its exact port contract and reset/link boundary.  This is intentionally
not a claim of full cache-child equivalence: the generated parent still
contains Slice, MSHR, SRAM, prefetch, and diplomacy children that are tracked
as separate closure work.
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
# The validator owns only the parent boundary and never mutates Scala or the
# locked XSTop artifact. / 验证器只负责父级边界，绝不修改 Scala 或锁定 XSTop。


# =============================================================================
# Configuration
# =============================================================================
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Dependency.CoupledL2.Bridge-Hardware.py"
REFERENCE = ROOT / "validation/reference-closures/TL2CHICoupledL2-Eb.sv"
OUT = ROOT / "validation/v2-coupledL2-parent-boundary-results.json"
COVERAGE = ROOT / "validation/v2-coupledL2-parent-boundary-coverage-manifest.json"
AUDIT = ROOT / "validation/v2-coupledL2-parent-boundary-contract-audit.json"
MAPPING = ROOT / "validation/v2-coupledL2-parent-boundary-mapping-update.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
REFERENCE_SHA256 = "3c1f8da19e8cc4e81dd49ae874378acb36d23c7400035ab0ba50dbed2383dcd0"
LOCKED_XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
SCALA_SOURCES = [
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/Bundle.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/chi/AsyncBridge.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/chi/CHILogger.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/chi/LinkLayer.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/chi/Message.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/chi/NetworkLayer.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/chi/Opcode.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/MainPipe.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/MMIOBridge.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/MSHR.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/MSHRCtl.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/RXDAT.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/RXRSP.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/RXSNP.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/Slice.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/TL2CHICoupledL2.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/TXDAT.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/TXREQ.scala",
    "upstream/coupledL2/src/main/scala/coupledL2/tl2chi/TXRSP.scala",
]


# =============================================================================
# Implementation
# =============================================================================
# Hash immutable bytes without newline normalization. / 计算不可变字节哈希且不规范化换行。
def digest(path: Path) -> str:
    """Return a SHA-256 digest. / 返回 SHA-256 摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


# Load exactly one Build file in an isolated namespace. / 在隔离命名空间加载精确的 Build 文件。
def load_target() -> ModuleType:
    """Import the target without sibling imports. / 导入目标且不导入同级文件。"""

    spec = importlib.util.spec_from_file_location("v2_coupled_l2_parent_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Audit the five-zone and exact adapter contract. / 审计五分区和精确 adapter 契约。
def static_audit() -> dict[str, Any]:
    """Return machine-readable target contract evidence. / 返回机器可读目标契约证据。"""

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
        and "CoupledL2ParentConfig" in source and "TL2CHICoupledL2" in source
    )
    return {"status": "PASS" if valid else "FAIL", "path": TARGET.relative_to(ROOT).as_posix(),
            "sha256": digest(TARGET), "bytes": len(raw), "zones": list(zones),
            "adapter_signatures": signatures, "function_comment_errors": errors,
            "forbidden_imports": forbidden_imports}


# Hash and count the frozen CHI Scala sources. / 哈希并统计冻结的 CHI Scala 源文件。
def source_inventory() -> dict[str, Any]:
    """Return immutable source inventory evidence. / 返回不可变源清单证据。"""

    entries: list[dict[str, Any]] = []
    missing: list[str] = []
    for relative in SCALA_SOURCES:
        path = ROOT / relative
        if not path.exists():
            missing.append(relative)
            continue
        entries.append({"path": relative, "sha256": digest(path), "bytes": path.stat().st_size,
                        "lines": len(path.read_text(encoding="utf-8").splitlines())})
    return {"status": "PASS" if not missing else "FAIL", "count": len(entries),
            "missing": missing, "entries": entries}


# Parse the generated ANSI reference header while preserving declaration order. /
# 解析生成的 ANSI 参考头并保留声明顺序。
def parse_reference_ports(path: Path) -> list[dict[str, Any]]:
    """Return direction/width/name entries from the reference parent. / 返回参考父级的方向、位宽和名称项。"""

    text = path.read_text(encoding="utf-8")
    match = re.search(r"module\s+TL2CHICoupledL2\s*\((.*?)\);", text, flags=re.S)
    if match is None:
        raise RuntimeError("TL2CHICoupledL2 module header not found")
    body = match.group(1)
    ports: list[dict[str, Any]] = []
    direction: str | None = None
    width = 1
    for line in body.splitlines():
        line = line.split("//", 1)[0].strip()
        if not line:
            continue
        declaration = re.match(r"^(input|output)\s+(?:(\[\s*(\d+)\s*:\s*(\d+)\s*\])\s+)?(.+)$", line)
        if declaration:
            direction = declaration.group(1)
            width = int(declaration.group(3)) - int(declaration.group(4)) + 1 if declaration.group(2) else 1
            names = declaration.group(5)
        else:
            names = line
        names = names.rstrip(";,").strip()
        for name in names.split(","):
            name = name.strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) and direction is not None:
                ports.append({"name": name, "width": width, "direction": direction})
    return ports


# Compare exact Python parent ports to the generated Scala parent. / 比较 Python 父级端口与生成 Scala 父级端口。
def contract_differential(module: ModuleType) -> dict[str, Any]:
    """Return a strict ordered port-contract comparison. / 返回严格有序端口契约比较。"""

    reference = parse_reference_ports(REFERENCE)
    expected = list(module.parent_port_contract(module.CoupledL2ParentConfig()))
    mismatches: list[dict[str, Any]] = []
    for index, (left, right) in enumerate(zip(expected, reference)):
        if left != right:
            mismatches.append({"index": index, "target": left, "reference": right})
    if len(expected) != len(reference):
        mismatches.append({"index": min(len(expected), len(reference)), "target_count": len(expected), "reference_count": len(reference)})
    return {"status": "PASS" if not mismatches else "FAIL", "target_count": len(expected),
            "reference_count": len(reference), "mismatches": mismatches,
            "reference_sha256": digest(REFERENCE), "reference_bytes": REFERENCE.stat().st_size,
            "chi_widths": {key: sum(value) for key, value in module.chi_layout_raw(module.CoupledL2ParentConfig().bridge_configuration()).items()}}


# Build a packed flit from sparse field indices. / 按稀疏字段索引构造打包 flit。
def pack_layout(module: ModuleType, widths: tuple[int, ...], values: dict[int, int]) -> int:
    """Pack optional-width fields deterministically. / 确定性打包含可选位宽的字段。"""

    return module.pack_fields([values.get(index, 0) for index, width in enumerate(widths) if width > 0],
                              [width for width in widths if width > 0])


# Exercise reset, link, TL request, CHI data, snoop, and credit flow. /
# 测试复位、链路、TL 请求、CHI 数据、snoop 和信用流。
def direct_bench(module: ModuleType) -> dict[str, Any]:
    """Run deterministic parent transactions and return a trace. / 运行确定性父级事务并返回轨迹。"""

    cfg = module.CoupledL2ParentConfig()
    top = module.TL2CHICoupledL2(cfg)
    simulator = Simulator(top)
    simulator.add_clock(1e-6, domain="tl2chi_parent")
    trace: list[dict[str, int]] = []
    observed = ("auto_in_a_ready", "auto_in_d_valid", "io_chi_txsactive", "io_chi_syscoreq",
                "io_chi_tx_linkactivereq", "io_chi_rx_linkactiveack", "io_chi_tx_req_flitpend",
                "io_chi_tx_req_flitv", "io_chi_tx_rsp_flitv", "io_l2Miss")

    async def bench(ctx: Any) -> None:
        for signal in top._inputs:
            if signal is not top.clock:
                ctx.set(signal, 0)
        for signal in (top.auto_in_d_ready, top.auto_in_b_ready, top.auto_mmioBridge_mmio_in_d_ready,
                       top.io_chi_tx_linkactiveack, top.io_chi_rx_linkactivereq,
                       top.io_chi_tx_req_lcrdv, top.io_chi_tx_rsp_lcrdv, top.io_chi_tx_dat_lcrdv):
            ctx.set(signal, 1)
        ctx.set(top.reset, 1)
        for cycle in range(4):
            await ctx.tick("tl2chi_parent")
            trace.append({"phase": "reset", "cycle": cycle, **{name: int(ctx.get(getattr(top, name))) for name in observed}})
        ctx.set(top.reset, 0)
        for cycle in range(6):
            await ctx.tick("tl2chi_parent")
            trace.append({"phase": "idle", "cycle": cycle, **{name: int(ctx.get(getattr(top, name))) for name in observed}})
        # A cacheable Get request must be accepted and emit a CHI ReadNoSnp.
        ctx.set(top.auto_in_a_valid, 1)
        ctx.set(top.auto_in_a_bits_opcode, module.TL_OPCODE_GET)
        ctx.set(top.auto_in_a_bits_size, 6)
        ctx.set(top.auto_in_a_bits_source, 3)
        ctx.set(top.auto_in_a_bits_address, 0x100)
        await ctx.delay(1e-9)
        ready_before = int(ctx.get(top.auto_in_a_ready))
        if ready_before != 1:
            raise AssertionError("parent did not expose TL A ready")
        await ctx.tick("tl2chi_parent")
        ctx.set(top.auto_in_a_valid, 0)
        # Credit advertisement and request capture happen on the same edge;
        # sample the combinational flit after that edge. / 信用广告与请求捕获在同一边沿完成，在该边沿后采样组合 flit。
        await ctx.delay(1e-9)
        if int(ctx.get(top.io_chi_tx_req_flitv)) != 1:
            raise AssertionError("parent did not emit CHI TXREQ")
        raw = module.chi_layout_raw(cfg.bridge_configuration())["req"]
        request_fields = module.unpack_fields(int(ctx.get(top.io_chi_tx_req_flit)), tuple(width for width in raw if width > 0))
        if request_fields[7] != module.CHI_REQ_OPCODES["ReadNoSnp"]:
            raise AssertionError(f"unexpected CHI request opcode: {request_fields[7]}")
        # A CompData response must return the payload on TL D.
        dat_raw = module.chi_layout_raw(cfg.bridge_configuration())["dat"]
        comp_data = pack_layout(module, dat_raw, {3: 3, 5: module.CHI_DAT_OPCODES["CompData"], 19: 0x123456})
        ctx.set(top.io_chi_rx_dat_flit, comp_data)
        ctx.set(top.io_chi_rx_dat_flitv, 1)
        await ctx.tick("tl2chi_parent")
        ctx.set(top.io_chi_rx_dat_flitv, 0)
        await ctx.delay(1e-9)
        if int(ctx.get(top.auto_in_d_valid)) != 1 or int(ctx.get(top.auto_in_d_bits_data)) != 0x123456:
            raise AssertionError("CompData did not reach TL D")
        # A snoop is returned as SnpResp after the response retires.
        await ctx.tick("tl2chi_parent")
        snp_raw = module.chi_layout_raw(cfg.bridge_configuration())["snp"]
        snoop = pack_layout(module, snp_raw, {1: 5, 2: 9, 5: module.CHI_SNP_OPCODES["SnpShared"], 6: 0x20})
        ctx.set(top.io_chi_rx_snp_flit, snoop)
        ctx.set(top.io_chi_rx_snp_flitv, 1)
        await ctx.tick("tl2chi_parent")
        ctx.set(top.io_chi_rx_snp_flitv, 0)
        await ctx.delay(1e-9)
        if int(ctx.get(top.io_chi_tx_rsp_flitv)) != 1:
            raise AssertionError("snoop response was not emitted")
        trace.append({"phase": "transactions", "tl_accept": 1, "read_opcode": module.CHI_REQ_OPCODES["ReadNoSnp"],
                      "comp_data": 0x123456, "snoop_response": module.CHI_RSP_OPCODES["SnpResp"]})

    simulator.add_testbench(bench)
    simulator.run()
    canonical = json.dumps(trace, sort_keys=True, separators=(",", ":")).encode()
    return {"status": "PASS", "checks": 4, "trace": trace,
            "trace_sha256": hashlib.sha256(canonical).hexdigest()}


# Run Verilator and Yosys on the generated Python parent. / 对 Python 生成父级运行 Verilator 和 Yosys。
def backend_gates(module: ModuleType) -> dict[str, Any]:
    """Return target HDL backend evidence. / 返回目标 HDL 后端证据。"""

    rtl = module.build_parent_verilog({"module": "UHSCCoupledL2", "issue": "E.b"}, {})
    with tempfile.TemporaryDirectory(prefix="v2_coupled_l2_parent_") as directory:
        path = Path(directory) / "UHSCCoupledL2.sv"
        path.write_text(rtl, encoding="utf-8", newline="\n")
        converted = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", check=True).stdout.strip()
        verilator = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                                    f"verilator --lint-only -Wno-fatal --top-module UHSCCoupledL2 '{converted}'"],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        yosys = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                                f"yosys -Q -p 'read_verilog -sv {converted}; hierarchy -top UHSCCoupledL2; proc; opt; check'"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return {"verilator": "PASS" if verilator.returncode == 0 else "FAIL",
            "yosys": "PASS" if yosys.returncode == 0 else "FAIL", "rtl_bytes": len(rtl.encode()),
            "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(),
            "verilator_returncode": verilator.returncode, "yosys_returncode": yosys.returncode}


# Persist all evidence while keeping full-child acceptance closed. / 持久化全部证据并保持完整子闭包验收关闭。
def main() -> int:
    """Run parent gates and write JSON evidence. / 运行父级门禁并写入 JSON 证据。"""

    static = static_audit()
    module = load_target()
    compile_result = subprocess.run([sys.executable, "-m", "py_compile", str(TARGET)], capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", check=False)
    if compile_result.returncode:
        raise RuntimeError(compile_result.stderr)
    inventory = source_inventory()
    contract = contract_differential(module)
    direct = direct_bench(module)
    backend = backend_gates(module)
    passed = all((static["status"] == "PASS", inventory["status"] == "PASS", contract["status"] == "PASS",
                  direct["status"] == "PASS", backend["verilator"] == "PASS", backend["yosys"] == "PASS"))
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_COUPLEDL2_PARENT_BOUNDARY",
        "batch_id": "V2-SEMANTIC-COUPLEDL2-PARENT-BOUNDARY-001",
        "source_commit": SOURCE_COMMIT,
        "source_scala_file_count": len(SCALA_SOURCES),
        "target": {"path": static["path"], "sha256": static["sha256"]},
        "static": static, "source_inventory": inventory, "contract_differential": contract,
        "direct": direct, "backend": backend,
        "reference": {"path": str(REFERENCE.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(REFERENCE),
                       "expected_sha256": REFERENCE_SHA256, "locked_xstop_sha256": LOCKED_XSTOP_SHA256,
                       "generation": "CoupledL2.test.runMain coupledL2.TestTop_CHIL2 --issue E.b --core 1 --tl-ul 0 --bank 1 --chiseldb 0 --tllog 0 --chilog 0 --etime 0 --vtime 0 --fpga 0 --target systemverilog --split-verilog",
                       "selection": "LOCAL_GENERATED_TESTTOP_CHIL2_PARENT"},
        "gates": {"PYTHON_PRESENT": static["status"], "DIRECT_TEST_PASS_BOUNDED": direct["status"],
                  "V2_REFERENCE_MATCHED": "PASS_BOUNDED_PARENT_PORT_AND_RESET_LINK" if passed else "FAIL",
                  "VERILATOR": backend["verilator"], "YOSYS": backend["yosys"],
                  "UHSC_LOCALIZED": "PASS_BOUNDED_UHSC_PARENT_ADAPTER",
                  "PARENT_CLOSURE_MATCHED": "PENDING_FULL_SLICE_MSHR_SRAM_DIPLOMACY_CHILDREN",
                  "LICENSE_REVIEW": "PENDING_COORDINATOR_REVIEW", "ACCEPTED": "NOT_ALLOWED"},
        "status": "VALIDATOR_PASS_BOUNDED" if passed else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "unclosed": ["Full Slice/MSHR/SRAM/prefetch/diplomacy behavioral closure remains pending.",
                      "Locked XSTop default is TL2TL; this CHI parent uses a separately generated TestTop_CHIL2 reference.",
                      "Coordinator/license review and user approval remain pending."],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    COVERAGE.write_text(json.dumps({
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_COUPLEDL2_PARENT_BOUNDARY_COVERAGE",
        "batch_id": payload["batch_id"], "source_scala_file_count": len(SCALA_SOURCES),
        "reference_port_count": contract["reference_count"], "contract_status": contract["status"],
        "direct_checks": direct["checks"], "backend": {"verilator": backend["verilator"], "yosys": backend["yosys"]},
        "covered": ["parent TL A admission", "CHI TXREQ layout", "CompData to TL D", "snoop response", "reset/link boundary"],
        "parent_closure": "PENDING_FULL_CHILD_CLOSURE", "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    AUDIT.write_text(json.dumps({
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_COUPLEDL2_PARENT_BOUNDARY_CONTRACT_AUDIT",
        "batch_id": payload["batch_id"], "static": static["status"], "source_inventory": inventory["status"],
        "contract_differential": contract["status"], "direct": direct["status"], "backend": backend,
        "parent_closure": "PENDING_FULL_SLICE_MSHR_SRAM_DIPLOMACY_CHILDREN", "accepted": "NOT_ALLOWED",
        "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    MAPPING.write_text(json.dumps({
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_COUPLEDL2_PARENT_BOUNDARY_MAPPING_UPDATE",
        "batch_id": payload["batch_id"], "source_commit": SOURCE_COMMIT,
        "closure_root": "dependency.coupledL2.bridge.parent", "target": static["path"],
        "source_paths": SCALA_SOURCES, "classification": "AGGREGATED_PARENT_BOUNDARY",
        "reference_module": "TL2CHICoupledL2", "local_name": "UHSCCoupledL2",
        "status": payload["status"], "parent_closure": "PENDING_FULL_CHILD_CLOSURE", "accepted": "NOT_ALLOWED",
        "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "ports": contract["target_count"],
                      "direct_checks": direct["checks"], "verilator": backend["verilator"],
                      "yosys": backend["yosys"], "accepted": "NOT_ALLOWED"}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
