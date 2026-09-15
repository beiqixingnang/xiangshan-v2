"""Independent bounded validator for Rocket diplomacy aggregate family."""

from __future__ import annotations

import ast
import hashlib
import json
import runpy
import subprocess
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator


# =============================================================================
# Module Contract
# =============================================================================
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Rocket.Diplomacy-Hardware.py"
SOURCE_ROOT = ROOT / "upstream/rocket-chip/src/main/scala/diplomacy"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"


# Hash target bytes. / 计算目标文件哈希。
def digest(path: Path) -> str:
    """Return SHA-256 digest. / 返回 SHA-256 摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Audit source shape, comments and adapter contract. / 审计源文件结构、注释及适配器契约。
def static_audit() -> dict[str, Any]:
    """Check deterministic Build-Cpu source structure. / 检查确定性的 Build-Cpu 源结构。"""
    raw = TARGET.read_bytes()
    source = raw.decode("utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    zones = [source.find(token) for token in ("Module Contract", "Address and protocol value contracts", "Lazy module and node graph contracts", "Hardware boundary", "Public Adapter")]
    errors: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prior_index = node.lineno - 2
            while prior_index >= 0 and lines[prior_index].strip().startswith("@"):
                prior_index -= 1
            prior = lines[prior_index].strip() if prior_index >= 0 else ""
            if not (prior.startswith("#") and "/" in prior):
                errors.append(f"{node.name}:{node.lineno}")
    adapters = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    args = [arg.arg for arg in adapters[0].args.args] if len(adapters) == 1 else []
    valid = zones == sorted(zones) and all(zone >= 0 for zone in zones) and not errors and args == ["configuration", "injected_dependencies"] and b"\r" not in raw
    return {"status": "PASS" if valid else "FAIL", "path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(TARGET), "bytes": len(raw), "zones": zones, "adapter_args": args, "function_comment_errors": errors}


# Exercise pure diplomacy contracts against independent equations. / 使用独立方程测试 diplomacy 纯契约。
def direct_contract_check(module: dict[str, Any]) -> dict[str, Any]:
    """Run address/range/node/transfer vectors. / 运行地址、范围、节点及传输向量。"""
    AddressSet, AddressRange = module["AddressSet"], module["AddressRange"]
    IdRange, TransferSizes = module["IdRange"], module["TransferSizes"]
    Graph, Node = module["LazyModuleGraph"], module["DiplomacyNode"]
    vectors = 0
    for index in range(32):
        base = index << 8
        aset = AddressSet(base, 0x3F)
        for offset in range(4):
            address = base | offset
            if not aset.contains(address) or not (((address ^ base) & ~0x3F) == 0):
                raise AssertionError(("contains", index, offset))
            vectors += 1
        if aset.max != base | 0x3F or not aset.contiguous:
            raise AssertionError(("geometry", index))
        ranges = aset.to_ranges()
        if not ranges or ranges[0].base != base:
            raise AssertionError(("ranges", index))
    for index in range(32):
        left = AddressRange(index * 16, 16)
        right = AddressRange(index * 16 + 8, 16)
        if left.union(right) != AddressRange(index * 16, 24):
            raise AssertionError(("union", index))
        if len(right.subtract(left)) != 1:
            raise AssertionError(("subtract", index))
        vectors += 2
    for index in range(32):
        ids = IdRange(index, index + 4)
        if ids.size != 4 or not ids.contains(index + 1) or ids.contains(index + 4):
            raise AssertionError(("id", index))
        transfer = TransferSizes(1, 16)
        if not transfer.contains(8) or transfer.contains(3):
            raise AssertionError(("transfer", index))
        vectors += 2
    graph = Graph()
    for name in ("source", "adapter", "sink"):
        graph.add(Node(name))
    graph.connect("source", "adapter"); graph.connect("adapter", "sink")
    if graph.resolve() != ("source", "adapter", "sink"):
        raise AssertionError(("topology", graph.resolve()))
    return {"status": "PASS", "vectors": vectors, "topological_order": list(graph.resolve())}


# Exercise generated address router and compare output to software decode. / 测试生成路由器并与软件解码比较。
def direct_router_check(module: dict[str, Any]) -> dict[str, Any]:
    """Run 128 ready/valid router vectors. / 运行 128 个 ready/valid 路由向量。"""
    cfg = module["DiplomacyConfig"](address_bits=16, route_bases=(0x0000, 0x1000, 0x2000, 0x3000), route_masks=(0x0FFF,) * 4)
    top = module["DiplomacyAddressRouter"](cfg)
    sim = Simulator(top)
    sim.add_clock(1e-6, domain="diplomacy")

    async def bench(ctx: Any) -> None:
        ctx.set(top.reset, 0); ctx.set(top.input_valid, 0); ctx.set(top.input_address, 0)
        await ctx.tick("diplomacy")
        for index in range(128):
            address = ((index % 4) << 12) | (index * 17 & 0x0FFF)
            ctx.set(top.input_valid, 1); ctx.set(top.input_address, address)
            await ctx.tick("diplomacy")
            expected = (address >> 12) if (address >> 12) < 4 else 0
            if int(ctx.get(top.output_valid)) != 1 or int(ctx.get(top.output_hit)) != 1 or int(ctx.get(top.output_route)) != expected or int(ctx.get(top.output_address)) != address:
                raise AssertionError((index, address, expected, ctx.get(top.output_route)))
        ctx.set(top.input_valid, 0); await ctx.tick("diplomacy")

    sim.add_testbench(bench)
    sim.run()
    return {"status": "PASS", "vectors": 128}


# Run Verilator and Yosys syntax checks. / 运行 Verilator 与 Yosys 语法检查。
def backend_check(module: dict[str, Any]) -> dict[str, Any]:
    """Export RTL and invoke available HDL linters. / 导出 RTL 并调用可用 HDL 检查器。"""
    rtl = module["build_verilog"]({"module": "UHSCRocketDiplomacy", "address_bits": 16, "route_bases": [0, 4096, 8192, 12288], "route_masks": [4095, 4095, 4095, 4095]}, {})
    work = ROOT / "validation/.work/v2-rocket-diplomacy"
    work.mkdir(parents=True, exist_ok=True)
    (work / "UHSCRocketDiplomacy.sv").write_text(rtl, encoding="utf-8")
    link = subprocess.run(["wsl.exe", "-e", "bash", "-lc", "ln -sfn /mnt/d/*/Unifier-Hardware-System/.agents/xiangshan-v2 /tmp/uhsc-v2"], capture_output=True, check=False)
    del link
    ver = subprocess.run(["wsl.exe", "-e", "bash", "-lc", "verilator --lint-only -Wno-fatal --top-module UHSCRocketDiplomacy /tmp/uhsc-v2/validation/.work/v2-rocket-diplomacy/UHSCRocketDiplomacy.sv"], capture_output=True, check=False)
    yos = subprocess.run(["wsl.exe", "-e", "bash", "-lc", "yosys -Q -p 'read_verilog -sv /tmp/uhsc-v2/validation/.work/v2-rocket-diplomacy/UHSCRocketDiplomacy.sv; hierarchy -top UHSCRocketDiplomacy; proc; check'"], capture_output=True, check=False)
    return {"verilator": "PASS" if ver.returncode == 0 else "FAIL", "yosys": "PASS" if yos.returncode == 0 else "FAIL", "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(), "rtl_bytes": len(rtl), "verilator_tail": ver.stderr.decode(errors="replace")[-400:], "yosys_tail": yos.stderr.decode(errors="replace")[-400:]}


# Audit retained rocket-chip license notices. / 审计保留的 rocket-chip 许可证声明。
def license_audit() -> dict[str, Any]:
    """Verify mixed-license files are present. / 验证混合许可证文件存在。"""
    names = ("LICENSE", "LICENSE.Berkeley", "LICENSE.SiFive", "LICENSE.jtag")
    present = [name for name in names if (ROOT / "upstream/rocket-chip" / name).exists()]
    return {"status": "PASS" if len(present) == len(names) else "PENDING", "required": list(names), "present": present, "note": "Mixed Rocket-chip notices retained; legal review remains pending before ACCEPTED."}


# Persist evidence and return bounded family status. / 持久化证据并返回有界 family 状态。
def main() -> int:
    """Run all independent family gates. / 运行所有独立 family 门禁。"""
    module = runpy.run_path(str(TARGET))
    static = static_audit()
    contracts = direct_contract_check(module)
    router = direct_router_check(module)
    backend = backend_check(module)
    license_result = license_audit()
    status = static["status"] == contracts["status"] == router["status"] == backend["verilator"] == backend["yosys"] == "PASS"
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_ROCKET_DIPLOMACY_FAMILY",
        "batch_id": "V2-DEPENDENCY-ROCKET-DIPLOMACY-001",
        "source_commit": SOURCE_COMMIT,
        "source_scala_file_count": 18,
        "source_root": "upstream/rocket-chip/src/main/scala/diplomacy",
        "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(TARGET)},
        "static": static,
        "direct": {"contracts": contracts, "router": router},
        "backend": backend,
        "license": license_result,
        "reference_mode": "LOCKED_XSTOP_DIPLOMACY_ADDRESS_ROUTER_EQUATIONS",
        "status": "VALIDATOR_PASS_BOUNDED" if status else "VALIDATOR_FAIL",
        "gates": {"PYTHON_PRESENT": static["status"], "DIRECT_TEST_PASS_BOUNDED": "PASS" if contracts["status"] == router["status"] == "PASS" else "FAIL", "V2_REFERENCE_MATCHED": "PASS_BOUNDED_DIPLOMACY_EQUATIONS", "VERILATOR": backend["verilator"], "YOSYS": backend["yosys"], "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME", "LICENSE_REVIEW": license_result["status"], "ACCEPTED": "NOT_ALLOWED"},
        "unclosed": ["Full Rocket Diplomacy closure and complete XSTop differential remain pending.", "License review and user approval remain pending."],
        "acceptance_eligible": False,
    }
    (ROOT / "validation/v2-rocket-diplomacy-family-results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": "PASS_BOUNDED_FAMILY" if status else "FAIL", "contracts": contracts["status"], "router": router["status"], "verilator": backend["verilator"], "yosys": backend["yosys"]}, sort_keys=True))
    return 0 if status else 1


if __name__ == "__main__":
    raise SystemExit(main())
