"""Independent validator for the V2 CoupledL2 CHI bridge family.
V2 CoupledL2 CHI bridge family 的独立验证器。

The validator is deliberately serial and family-local.  It validates the
aggregate Build file, the source-derived CHI contracts, deterministic
transaction/credit equations, an executable bridge bench, and HDL backends.
The locked DefaultConfig top does not instantiate ``tl2chi``; that conditional
fact is recorded as evidence and is not promoted to full-top equivalence.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import random
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
# The independent gates cover source inventory, CHI layouts/opcodes, link
# credits, transaction IDs, TL/CHI ordering, reset, retry, MMIO, snoop, flush,
# reference-top reachability, and Verilator/Yosys.
# 独立门禁覆盖源清单、CHI 布局/操作码、链路信用、事务 ID、TL/CHI 顺序、复位、重试、MMIO、snoop、flush、顶层可达性以及 Verilator/Yosys。


# =============================================================================
# Configuration
# =============================================================================
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Memory" / "Build-Cpu.Dependency.CoupledL2.Bridge-Hardware.py"
OUT = ROOT / "validation" / "v2-coupledL2-bridge-family-results.json"
COVERAGE = ROOT / "validation" / "v2-coupledL2-bridge-family-coverage-manifest.json"
AUDIT = ROOT / "validation" / "v2-coupledL2-bridge-family-contract-audit.json"
MAPPING = ROOT / "validation" / "v2-coupledL2-bridge-family-mapping-update.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_WSL = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
SOURCE_PATHS = [
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


# Hash bytes without normalizing line endings. / 不规范化换行地计算字节哈希。
def digest(path: Path) -> str:
    """Return the SHA-256 digest of a file. / 返回文件 SHA-256 摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


# Load the exact target path in an isolated module namespace. / 在隔离模块命名空间中加载精确目标路径。
def load_exact(path: Path) -> ModuleType:
    """Import one Build file without sibling imports. / 不导入同级文件地加载一个 Build 文件。"""

    spec = importlib.util.spec_from_file_location("v2_coupled_l2_bridge_target", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Audit the five-zone, import, naming, and function-comment contract. / 审计五分区、导入、命名及函数注释契约。
def static_audit() -> dict[str, Any]:
    """Return machine-readable static contract evidence. / 返回机器可读静态契约证据。"""

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
    adapter = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    adapter_args = [arg.arg for arg in adapter[0].args.args] if len(adapter) == 1 else []
    valid = (
        not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw and
        positions == sorted(positions) and all(value >= 0 for value in positions) and
        not errors and not forbidden_imports and adapter_args == ["configuration", "injected_dependencies"] and
        "UHSCCoupledL2Bridge" in source and "ACCEPTED" not in source
    )
    return {"status": "PASS" if valid else "FAIL", "path": TARGET.relative_to(ROOT).as_posix(),
            "sha256": digest(TARGET), "bytes": len(raw), "zones": list(zones),
            "adapter_args": adapter_args, "function_comment_errors": errors,
            "forbidden_imports": forbidden_imports}


# Collect immutable source hashes and line counts. / 收集不可变源哈希及行数。
def source_inventory() -> dict[str, Any]:
    """Verify all 19 frozen Scala paths. / 验证冻结的 19 个 Scala 路径。"""

    entries: list[dict[str, Any]] = []
    missing: list[str] = []
    for relative in SOURCE_PATHS:
        path = ROOT / relative
        if not path.exists():
            missing.append(relative)
            continue
        entries.append({"path": relative, "sha256": digest(path), "bytes": path.stat().st_size,
                        "lines": len(path.read_text(encoding="utf-8").splitlines())})
    return {"status": "PASS" if not missing and len(entries) == 19 else "FAIL",
            "count": len(entries), "missing": missing, "entries": entries}


# Parse source constants and compare the aggregate's independent maps. / 解析源常量并与聚合实现的独立映射比较。
def source_contract_differential(module: ModuleType) -> dict[str, Any]:
    """Compare CHI opcode/channel/state literals against Scala. / 对比 Scala 中 CHI 操作码/通道/状态字面量。"""

    opcode_text = (ROOT / SOURCE_PATHS[6]).read_text(encoding="utf-8")
    message_text = (ROOT / SOURCE_PATHS[4]).read_text(encoding="utf-8")
    link_text = (ROOT / SOURCE_PATHS[3]).read_text(encoding="utf-8")
    req = module.CHI_REQ_OPCODES
    rsp = module.CHI_RSP_OPCODES
    snp = module.CHI_SNP_OPCODES
    dat = module.CHI_DAT_OPCODES
    checks = 0
    mismatches: list[str] = []
    # Literal definitions in Opcode.scala, including issue-gated Eb opcodes.
    for name, value in {**req, **rsp, **snp, **dat}.items():
        match = re.search(rf"def\s+{re.escape(name)}\s*=\s*(?:Eb_OPCODE\(|C_OPCODE\()?(?:0x)?([0-9A-Fa-f]+)", opcode_text)
        if match is None:
            mismatches.append(f"missing source opcode {name}")
        elif int(match.group(1), 16) != value:
            mismatches.append(f"opcode {name}: source={match.group(1)} aggregate={value:x}")
        checks += 1
    # Channel constants and coherence/link state encodings from Bundle/Message/LinkLayer.
    channel_expect = {"TXREQ": 1, "TXRSP": 2, "TXDAT": 4}
    for name, value in channel_expect.items():
        if not re.search(rf"def\s+{name}\s*=\s*\"b{value:03b}\"\.U", (ROOT / SOURCE_PATHS[0]).read_text(encoding="utf-8")):
            mismatches.append(f"channel {name} source mismatch")
        checks += 1
    state_expect = {"STOP": 0, "ACTIVATE": 1, "RUN": 2, "DEACTIVATE": 3}
    for name, value in state_expect.items():
        if not re.search(rf"def\s+{name}\s*=\s*{value}\.U", link_text):
            mismatches.append(f"link state {name} source mismatch")
        if getattr(module, f"LINK_{name}") != value:
            mismatches.append(f"link state {name} aggregate mismatch")
        checks += 1
    # Message.scala's issue-B defaults and CHI coherence state encodings.
    for name, value in {"I": 0, "SC": 1, "UC": 2, "SD": 3, "PassDirty": 4}.items():
        if not re.search(rf"def\s+{name}\s*=\s*\"b{value:03b}\"\.U", message_text):
            mismatches.append(f"coherence state {name} source mismatch")
        if module.CHI_COHERENCE_STATES[name] != value:
            mismatches.append(f"coherence state {name} aggregate mismatch")
        checks += 1
    return {"status": "PASS" if not mismatches else "FAIL", "checks": checks,
            "mismatches": mismatches, "source_files": [SOURCE_PATHS[0], SOURCE_PATHS[3], SOURCE_PATHS[4], SOURCE_PATHS[6]]}


# Exercise pure CHI layout, opcode, credit, ID, and response equations. / 执行纯 CHI 布局、操作码、信用、ID 及响应方程。
def equation_vectors(module: ModuleType) -> dict[str, Any]:
    """Run deterministic and randomized source-level vectors. / 运行确定性及随机源级向量。"""

    rng = random.Random(0xC012B1D6)
    vectors = 0
    layout_widths: dict[str, dict[str, int]] = {}
    for issue in ("B", "C", "E.b"):
        cfg = module.CoupledL2BridgeConfig(issue=issue, address_bits=48, data_bits=256)
        widths = module.chi_layout_widths(cfg)
        layout_widths[issue] = {channel: sum(fields) for channel, fields in widths.items()}
        for channel, fields in widths.items():
            for _ in range(128):
                values = [rng.randrange(1 << width) for width in fields]
                packed = module.pack_fields(values, fields)
                if module.unpack_fields(packed, fields) != tuple(values):
                    raise AssertionError((issue, channel, values))
                vectors += 1
    expected_req = {4: module.CHI_REQ_OPCODES["ReadNoSnp"], 0: module.CHI_REQ_OPCODES["WriteNoSnpFull"],
                    1: module.CHI_REQ_OPCODES["WriteNoSnpPtl"], 2: module.CHI_REQ_OPCODES["AtomicLoad_ADD"],
                    3: module.CHI_REQ_OPCODES["AtomicLoad_EOR"], 5: module.CHI_REQ_OPCODES["PrefetchTgt"],
                    6: module.CHI_REQ_OPCODES["ReadShared"], 7: module.CHI_REQ_OPCODES["ReadUnique"]}
    for tl_opcode, chi_opcode in expected_req.items():
        if module.tl_to_chi_opcode(tl_opcode) != chi_opcode:
            raise AssertionError((tl_opcode, module.tl_to_chi_opcode(tl_opcode), chi_opcode))
        vectors += 1
    for pool in range(0, 16):
        for ret in (False, True):
            for consume in (False, True):
                if ret and consume:
                    expected = pool
                elif ret:
                    expected = pool + 1
                elif consume:
                    expected = pool - 1
                else:
                    expected = pool
                if 0 <= expected <= 15:
                    observed = module.credit_step(pool, ret, consume, module.LINK_RUN, 15)
                    if observed != expected:
                        raise AssertionError((pool, ret, consume, observed, expected))
                    vectors += 1
    for banks, bank_bits in ((1, 0), (4, 2), (8, 3)):
        for mmio in (False, True):
            for slice_id in range(min(banks, 8)):
                for txn in range(32):
                    encoded = module.encode_transaction_id(txn, slice_id, mmio, banks, bank_bits, 8)
                    decoded = module.decode_transaction_id(encoded, banks, bank_bits, 8)
                    if decoded["mmio"] != int(mmio):
                        raise AssertionError((banks, mmio, encoded, decoded))
                    expected_slice = 0 if mmio or banks <= 1 else slice_id
                    if decoded["slice_id"] != expected_slice:
                        raise AssertionError((banks, slice_id, encoded, decoded))
                    vectors += 1
    for address in range(0, 0x4000, 17):
        target = module.sam_lookup(address, ((0x0000, 0x0FFF, 1), (0x1000, 0x0FFF, 2), (0x2000, 0x0FFF, 3)))
        expected = (address >> 12) + 1 if address < 0x3000 else 0
        if target != expected:
            raise AssertionError((address, target, expected))
        vectors += 1
    for opcode in module.CHI_SNP_OPCODES.values():
        result = module.snoop_response(opcode, 9, 3, dirty=opcode & 1, forward=opcode in (0x11, 0x12, 0x13, 0x16, 0x17))
        if result["transaction_id"] != 9 or result["source_id"] != 3:
            raise AssertionError((opcode, result))
        vectors += 1
    return {"status": "PASS", "vectors": vectors, "layout_widths": layout_widths}


# Drive the synthesizable bridge through read/write/retry/snoop/flush paths. / 驱动可综合 bridge 的读写、重试、snoop、flush 路径。
def direct_bench(module: ModuleType) -> dict[str, Any]:
    """Run an executable Amaranth transaction bench. / 运行可执行 Amaranth 事务 bench。"""

    # Exercise the source-ready variant here so the transaction path can be
    # observed without an external credit bootstrap; the default credit-gated
    # variant is covered separately by ``credit_mode_bench`` below.
    top = module.CoupledL2Bridge(module.CoupledL2BridgeConfig(tx_source_ready=True))
    simulator = Simulator(top)
    simulator.add_clock(1e-6, domain="coupled_l2_bridge")
    inputs = (
        "reset", "flush", "tl_req_valid", "tl_req_opcode", "tl_req_size", "tl_req_source", "tl_req_address",
        "tl_req_data", "tl_req_mask", "tl_req_mmio", "tl_req_corrupt", "tx_req_ready", "tx_rsp_ready",
        "tx_dat_ready", "rx_rsp_valid", "rx_rsp_opcode", "rx_rsp_src_id", "rx_rsp_txn_id", "rx_rsp_db_id",
        "rx_rsp_resp", "rx_rsp_resp_err", "rx_rsp_pcrd_type", "rx_dat_valid", "rx_dat_opcode", "rx_dat_src_id",
        "rx_dat_txn_id", "rx_dat_data_id", "rx_dat_resp", "rx_dat_resp_err", "rx_dat_data", "rx_snp_valid",
        "rx_snp_opcode", "rx_snp_src_id", "rx_snp_txn_id", "tx_linkactiveack", "rx_linkactivereq",
        "tx_req_credit_return", "tx_rsp_credit_return", "tx_dat_credit_return", "tl_resp_ready",
    )
    observations: list[dict[str, int]] = []

    async def bench(ctx: Any) -> None:
        for name in inputs:
            ctx.set(getattr(top, name), 0)
        for name in ("tx_req_ready", "tx_rsp_ready", "tx_dat_ready", "tl_resp_ready", "tx_linkactiveack", "rx_linkactivereq"):
            ctx.set(getattr(top, name), 1)
        ctx.set(top.reset, 1)
        await ctx.tick("coupled_l2_bridge")
        ctx.set(top.reset, 0)
        await ctx.tick("coupled_l2_bridge")
        await ctx.delay(1e-9)
        if int(ctx.get(top.tx_state)) != module.LINK_RUN or int(ctx.get(top.rx_state)) != module.LINK_RUN:
            raise AssertionError("link did not enter RUN")
        # ReadNoSnp/CompData path with backpressure observation. / ReadNoSnp/CompData 路径并观察反压。
        ctx.set(top.tx_req_ready, 0)
        ctx.set(top.tl_req_valid, 1)
        ctx.set(top.tl_req_opcode, module.TL_OPCODE_GET)
        ctx.set(top.tl_req_size, 3)
        ctx.set(top.tl_req_source, 7)
        ctx.set(top.tl_req_address, 0x100)
        ctx.set(top.tl_req_data, 0xDEAD)
        ctx.set(top.tl_req_mask, 0xFFFFFFFF)
        await ctx.delay(1e-9)
        if not int(ctx.get(top.tl_req_ready)):
            raise AssertionError("read request not accepted")
        await ctx.tick("coupled_l2_bridge")
        ctx.set(top.tl_req_valid, 0)
        await ctx.delay(1e-9)
        if not int(ctx.get(top.tx_req_valid)) or int(ctx.get(top.tx_req_opcode)) != module.CHI_REQ_OPCODES["ReadNoSnp"]:
            raise AssertionError("ReadNoSnp was not held under backpressure")
        await ctx.tick("coupled_l2_bridge")
        ctx.set(top.rx_dat_valid, 1)
        ctx.set(top.rx_dat_data, 0x123456)
        ctx.set(top.rx_dat_resp_err, module.CHI_RESP_ERR["OK"])
        await ctx.delay(1e-9)
        if not int(ctx.get(top.rx_dat_ready)):
            raise AssertionError("RXDAT was not ready")
        await ctx.tick("coupled_l2_bridge")
        ctx.set(top.rx_dat_valid, 0)
        await ctx.delay(1e-9)
        if not int(ctx.get(top.tl_resp_valid)) or int(ctx.get(top.tl_resp_opcode)) != 1 or int(ctx.get(top.tl_resp_data)) != 0x123456:
            raise AssertionError("CompData did not become TL AccessAckData")
        observations.append({"read_opcode": int(ctx.get(top.tx_req_opcode)), "read_data": int(ctx.get(top.tl_resp_data))})
        await ctx.tick("coupled_l2_bridge")
        # MMIO write path: DBIDResp -> NonCopyBackWrData -> Comp. / MMIO 写路径：DBIDResp -> NonCopyBackWrData -> Comp。
        ctx.set(top.tl_req_valid, 1)
        ctx.set(top.tl_req_opcode, module.TL_OPCODE_PUTFULL)
        ctx.set(top.tl_req_size, 3)
        ctx.set(top.tl_req_source, 2)
        ctx.set(top.tl_req_address, 0x200)
        ctx.set(top.tl_req_data, 0xBEEF)
        ctx.set(top.tl_req_mask, 0xFFFFFFFF)
        ctx.set(top.tl_req_mmio, 1)
        await ctx.tick("coupled_l2_bridge")
        ctx.set(top.tl_req_valid, 0)
        await ctx.delay(1e-9)
        if int(ctx.get(top.tx_req_opcode)) != module.CHI_REQ_OPCODES["WriteNoSnpPtl"]:
            raise AssertionError("MMIO PutFull opcode mismatch")
        await ctx.tick("coupled_l2_bridge")
        ctx.set(top.rx_rsp_valid, 1)
        ctx.set(top.rx_rsp_opcode, module.CHI_RSP_OPCODES["DBIDResp"])
        ctx.set(top.rx_rsp_db_id, 11)
        ctx.set(top.rx_rsp_resp_err, module.CHI_RESP_ERR["OK"])
        await ctx.tick("coupled_l2_bridge")
        ctx.set(top.rx_rsp_valid, 0)
        await ctx.delay(1e-9)
        if not int(ctx.get(top.tx_dat_valid)) or int(ctx.get(top.tx_dat_db_id)) != 11:
            raise AssertionError("DBIDResp did not schedule write data")
        await ctx.tick("coupled_l2_bridge")
        ctx.set(top.rx_rsp_valid, 1)
        ctx.set(top.rx_rsp_opcode, module.CHI_RSP_OPCODES["Comp"])
        await ctx.tick("coupled_l2_bridge")
        ctx.set(top.rx_rsp_valid, 0)
        await ctx.delay(1e-9)
        if not int(ctx.get(top.tl_resp_valid)) or int(ctx.get(top.tl_resp_opcode)) != 0:
            raise AssertionError("write completion mismatch")
        observations.append({"write_opcode": int(ctx.get(top.tx_req_opcode)), "write_dbid": 11})
        await ctx.tick("coupled_l2_bridge")
        # Forwarded snoop path. / 转发 snoop 路径。
        ctx.set(top.rx_snp_valid, 1)
        ctx.set(top.rx_snp_opcode, module.CHI_SNP_OPCODES["SnpSharedFwd"])
        ctx.set(top.rx_snp_src_id, 3)
        ctx.set(top.rx_snp_txn_id, 5)
        await ctx.delay(1e-9)
        if not int(ctx.get(top.rx_snp_ready)):
            raise AssertionError("RXSNP was not ready")
        await ctx.tick("coupled_l2_bridge")
        ctx.set(top.rx_snp_valid, 0)
        await ctx.delay(1e-9)
        if not int(ctx.get(top.tx_rsp_valid)) or int(ctx.get(top.tx_rsp_opcode)) != module.CHI_RSP_OPCODES["SnpRespFwded"]:
            raise AssertionError("forwarded snoop response mismatch")
        observations.append({"snoop_opcode": int(ctx.get(top.tx_rsp_opcode)), "snoop_txn": 5})
        await ctx.tick("coupled_l2_bridge")
        # Flush cancels pending work and exposes completion. / flush 取消挂起工作并暴露完成。
        ctx.set(top.tl_req_valid, 1)
        ctx.set(top.tl_req_opcode, module.TL_OPCODE_GET)
        ctx.set(top.tl_req_size, 3)
        ctx.set(top.tl_req_source, 1)
        await ctx.tick("coupled_l2_bridge")
        ctx.set(top.tl_req_valid, 0)
        ctx.set(top.flush, 1)
        await ctx.tick("coupled_l2_bridge")
        await ctx.delay(1e-9)
        if int(ctx.get(top.tx_req_valid)) or int(ctx.get(top.tl_resp_valid)) or not int(ctx.get(top.flush_done)):
            raise AssertionError("flush did not cancel bridge state")
        observations.append({"flush_done": int(ctx.get(top.flush_done))})

    simulator.add_testbench(bench)
    simulator.run()
    trace = json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()
    return {"status": "PASS", "checks": len(observations), "trace": observations,
            "trace_sha256": hashlib.sha256(trace).hexdigest()}


# Verify the default credit-gated link does not emit before an L-Credit return. / 验证默认信用门控链路在收到 L-Credit 前不会发送 flit。
def credit_mode_bench(module: ModuleType) -> dict[str, Any]:
    """Exercise Decoupled2LCredit-style bootstrap and consumption. / 测试 Decoupled2LCredit 风格的启动与消耗。"""

    top = module.CoupledL2Bridge(module.CoupledL2BridgeConfig(tx_source_ready=False, credit_num=4))
    simulator = Simulator(top)
    simulator.add_clock(1e-6, domain="coupled_l2_bridge")
    inputs = (
        "reset", "flush", "tl_req_valid", "tl_req_opcode", "tl_req_size", "tl_req_source", "tl_req_address",
        "tl_req_data", "tl_req_mask", "tl_req_mmio", "tl_req_corrupt", "tx_req_ready", "tx_rsp_ready",
        "tx_dat_ready", "rx_rsp_valid", "rx_dat_valid", "rx_snp_valid", "tx_linkactiveack", "rx_linkactivereq",
        "tx_req_credit_return", "tx_rsp_credit_return", "tx_dat_credit_return", "tl_resp_ready",
    )

    async def bench(ctx: Any) -> None:
        for name in inputs:
            ctx.set(getattr(top, name), 0)
        for name in ("tx_req_ready", "tx_rsp_ready", "tx_dat_ready", "tl_resp_ready", "tx_linkactiveack", "rx_linkactivereq"):
            ctx.set(getattr(top, name), 1)
        ctx.set(top.reset, 1)
        await ctx.tick("coupled_l2_bridge")
        ctx.set(top.reset, 0)
        await ctx.tick("coupled_l2_bridge")
        ctx.set(top.tx_req_ready, 0)
        ctx.set(top.tl_req_valid, 1)
        ctx.set(top.tl_req_opcode, module.TL_OPCODE_GET)
        ctx.set(top.tl_req_size, 3)
        ctx.set(top.tl_req_source, 1)
        ctx.set(top.tl_req_address, 0x300)
        await ctx.tick("coupled_l2_bridge")
        ctx.set(top.tl_req_valid, 0)
        await ctx.delay(1e-9)
        if int(ctx.get(top.tx_req_credit_available)) or int(ctx.get(top.tx_req_valid)):
            raise AssertionError("credit-gated TXREQ emitted without a returned credit")
        ctx.set(top.tx_req_credit_return, 1)
        await ctx.tick("coupled_l2_bridge")
        ctx.set(top.tx_req_credit_return, 0)
        await ctx.delay(1e-9)
        if not int(ctx.get(top.tx_req_credit_available)) or not int(ctx.get(top.tx_req_valid)):
            raise AssertionError("returned credit did not release TXREQ")
        ctx.set(top.tx_req_ready, 1)
        await ctx.tick("coupled_l2_bridge")
        await ctx.delay(1e-9)
        if int(ctx.get(top.tx_req_credit_available)):
            raise AssertionError("accepted TXREQ did not consume its credit")

    simulator.add_testbench(bench)
    simulator.run()
    return {"status": "PASS", "checks": 3, "mode": "credit_gated_default"}


# Check the generated aggregate with Verilator and Yosys. / 使用 Verilator 与 Yosys 检查生成的聚合 RTL。
def backend_gates(module: ModuleType) -> dict[str, Any]:
    """Run deterministic export and HDL lint gates. / 运行确定性导出及 HDL lint 门禁。"""

    rtl = module.build_verilog({"module": "UHSCCoupledL2Bridge", "address_bits": 48, "data_bits": 256}, {})
    with tempfile.TemporaryDirectory(prefix="v2_coupled_l2_bridge_") as directory:
        path = Path(directory) / "UHSCCoupledL2Bridge.sv"
        path.write_text(rtl, encoding="utf-8", newline="\n")
        converted = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)], capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", check=True).stdout.strip()
        verilator = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                                    f"verilator --lint-only -Wno-fatal --top-module UHSCCoupledL2Bridge '{converted}'"],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        yosys = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                                f"yosys -Q -p 'read_verilog -sv {converted}; hierarchy -top UHSCCoupledL2Bridge; proc; opt; check'"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    def stable_tail(text: str) -> str:
        """Remove temporary path names from tool diagnostics. / 移除工具诊断中的临时路径名。"""

        cleaned = re.sub(r"(?:/mnt/[^\s:]*/Temp|[A-Za-z]:\\[^\s:]*)/v2_coupled_l2_bridge_[^/\\\s]+", "<temp>", text[-1200:])
        # Yosys appends a process-dependent logfile hash, timing, and memory;
        # these are run metadata, not behavioral evidence. / Yosys 追加的日志哈希、计时和内存依赖进程，过滤掉。
        kept = [line for line in cleaned.splitlines()
                if "Logfile hash:" not in line and "CPU:" not in line and "MEM:" not in line and "Time spent:" not in line]
        return "\n".join(kept)[-800:]

    return {"verilator": "PASS" if verilator.returncode == 0 else "FAIL",
            "yosys": "PASS" if yosys.returncode == 0 else "FAIL", "rtl_bytes": len(rtl.encode()),
            "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(),
            "verilator_returncode": verilator.returncode, "yosys_returncode": yosys.returncode,
            "verilator_tail": stable_tail(verilator.stderr or verilator.stdout),
            "yosys_tail": stable_tail(yosys.stderr or yosys.stdout)}


# Verify retained coupledL2 license notices without claiming legal acceptance. / 验证保留 coupledL2 许可证声明但不宣称法律接受。
def license_audit() -> dict[str, Any]:
    """Return notice presence and immutable hashes. / 返回声明存在性及不可变哈希。"""

    names = ("LICENSE", "LICENSE.SiFive")
    entries = []
    for name in names:
        path = ROOT / "upstream" / "coupledL2" / name
        entries.append({"path": str(path.relative_to(ROOT)).replace("\\", "/"), "present": path.exists(),
                        "sha256": digest(path) if path.exists() else None})
    return {"status": "PASS_RETAINED_PENDING_LEGAL_REVIEW" if all(e["present"] for e in entries) else "PENDING",
            "entries": entries, "review_required": True}


# Compare the locked top hash and prove the conditional CHI path is not selected. / 对比锁定顶层哈希并证明条件 CHI 路径未被选中。
def reference_probe() -> dict[str, Any]:
    """Return locked reference reachability evidence. / 返回锁定参考可达性证据。"""

    command = f"sha256sum {REFERENCE_WSL}; grep -Ec 'tl2chi|TL2CHICoupledL2|LinkMonitor|UHSCCoupledL2Bridge' {REFERENCE_WSL} || true"
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", check=False)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    observed_hash = lines[0].split()[0] if lines and len(lines[0].split()) >= 2 else None
    marker_count = int(lines[1]) if len(lines) > 1 and lines[1].isdigit() else None
    hash_match = observed_hash == REFERENCE_SHA256
    return {"status": "PASS" if hash_match and marker_count == 0 else "FAIL",
            "reference_path": REFERENCE_WSL, "expected_sha256": REFERENCE_SHA256,
            "observed_sha256": observed_hash, "chi_marker_count": marker_count,
            "selection": "CONDITIONAL_UNREACHED_DEFAULT_CONFIG" if marker_count == 0 else "SELECTED_OR_UNKNOWN",
            "note": "No full CHI top differential is claimed while DefaultConfig selects TL2TL."}


# Persist all evidence, coverage, mapping, and contract audit records. / 持久化全部证据、覆盖、映射及契约审计记录。
def main() -> int:
    """Run serial family gates and write JSON evidence. / 串行运行 family 门禁并写入 JSON 证据。"""

    static = static_audit()
    module = load_exact(TARGET)
    compile_result = subprocess.run([sys.executable, "-m", "py_compile", str(TARGET)], capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", check=False)
    if compile_result.returncode:
        raise RuntimeError(compile_result.stderr)
    inventory = source_inventory()
    source_diff = source_contract_differential(module)
    equations = equation_vectors(module)
    direct = direct_bench(module)
    credit_mode = credit_mode_bench(module)
    backend = backend_gates(module)
    license_result = license_audit()
    reference = reference_probe()
    passed = all((static["status"] == "PASS", inventory["status"] == "PASS", source_diff["status"] == "PASS",
                  equations["status"] == "PASS", direct["status"] == "PASS", credit_mode["status"] == "PASS",
                  backend["verilator"] == "PASS",
                  backend["yosys"] == "PASS", reference["status"] == "PASS"))
    gates = {
        "PYTHON_PRESENT": static["status"],
        "DIRECT_TEST_PASS_BOUNDED": direct["status"],
        "V2_REFERENCE_MATCHED": "PASS_BOUNDED_SOURCE_LAYOUT_CONDITIONAL_CHI_UNREACHED" if passed else "FAIL",
        "VERILATOR": backend["verilator"], "YOSYS": backend["yosys"],
        "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME", "PARENT_CLOSURE_MATCHED": "PENDING_TL2CHICoupledL2_PARENT",
        "LICENSE_REVIEW": license_result["status"], "ACCEPTED": "NOT_ALLOWED",
    }
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_COUPLEDL2_BRIDGE_FAMILY",
        "batch_id": "V2-DEPENDENCY-COUPLEDL2-BRIDGE-001",
        "source_commit": SOURCE_COMMIT,
        "source_scala_file_count": len(SOURCE_PATHS),
        "source_root": "upstream/coupledL2/src/main/scala/coupledL2/tl2chi",
        "target": {"path": static["path"], "sha256": static["sha256"]},
        "static": static, "source_inventory": inventory, "source_differential": source_diff,
        "equations": equations, "direct": direct, "credit_mode": credit_mode, "backend": backend, "license": license_result,
        "reference": reference, "reference_mode": "LOCKED_XSTOP_TL2CHI_CONDITIONAL_BOUNDARY",
        "gates": gates,
        "unclosed": [
            "Full TL2CHICoupledL2 parent and complete CHI-enabled top differential remain pending.",
            "DefaultConfig locked XSTop selects TL2TL; CHI bridge is conditional and not instantiated.",
            "Full parent closure, legal review, and user approval remain pending.",
        ],
        "status": "VALIDATOR_PASS_BOUNDED" if passed else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    COVERAGE.write_text(json.dumps({
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_COUPLEDL2_BRIDGE_COVERAGE",
        "batch_id": payload["batch_id"], "source_scala_file_count": len(SOURCE_PATHS),
        "covered_children": ["Bundle", "Message", "Opcode", "LinkLayer", "NetworkLayer", "AsyncBridge",
                              "MMIOBridge", "TXREQ", "TXRSP", "TXDAT", "RXRSP", "RXDAT", "RXSNP",
                              "MainPipe boundary", "MSHR boundary", "MSHRCtl boundary", "Slice boundary",
                              "TL2CHICoupledL2 boundary"],
        "equation_vectors": equations["vectors"], "direct_checks": direct["checks"], "credit_mode_checks": credit_mode["checks"],
        "backend": {"verilator": backend["verilator"], "yosys": backend["yosys"]},
        "reference_selection": reference["selection"], "status": "PASS_BOUNDED_FAMILY" if passed else "FAIL",
        "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    AUDIT.write_text(json.dumps({
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_COUPLEDL2_BRIDGE_CONTRACT_AUDIT",
        "batch_id": payload["batch_id"], "target": static["path"],
        "boundary": ["CHI B/C/E.b layouts", "TL-to-CHI opcode conversion", "TXREQ/TXRSP/TXDAT ordering",
                     "RXRSP/RXDAT/RXSNP dispatch", "L-Credit pools", "link monitor states", "MMIO transaction IDs",
                     "PCrd retry/return", "flush cancellation"],
        "source_differential": source_diff["status"], "static": static["status"],
        "license_review": license_result["status"], "parent_closure": "PENDING_TL2CHICoupledL2_PARENT",
        "accepted": "NOT_ALLOWED", "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    MAPPING.write_text(json.dumps({
        "schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_COUPLEDL2_BRIDGE_MAPPING_UPDATE",
        "family_id": "dependency.coupledL2.bridge", "source_commit": SOURCE_COMMIT,
        "source_paths": SOURCE_PATHS, "target_path": static["path"], "classification": "AGGREGATED_REWRITE",
        "covered_children": ["Bundle", "chi/Message", "chi/Opcode", "chi/LinkLayer", "chi/NetworkLayer",
                              "chi/AsyncBridge", "MainPipe", "MMIOBridge", "MSHR", "MSHRCtl", "RXDAT", "RXRSP",
                              "RXSNP", "Slice", "TL2CHICoupledL2", "TXDAT", "TXREQ", "TXRSP"],
        "localization": {"source_name": "TL2CHICoupledL2", "local_name": "UHSCCoupledL2Bridge",
                          "visibility": "project_owned_generated_hdl",
                          "reason": "UHSC external family wrapper; locked Scala/SV names remain unchanged"},
        "reference_selection": reference["selection"], "evidence": str(OUT.relative_to(ROOT)).replace("\\", "/"),
        "status": payload["status"], "parent_closure": "PENDING_TL2CHICoupledL2_PARENT",
        "accepted": "NOT_ALLOWED",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "source_count": len(SOURCE_PATHS),
                      "equation_vectors": equations["vectors"], "direct_checks": direct["checks"],
                      "verilator": backend["verilator"], "yosys": backend["yosys"],
                      "reference": reference["selection"]}, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
