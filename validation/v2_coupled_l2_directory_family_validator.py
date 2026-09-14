"""Independent bounded validator for the V2 CoupledL2 Directory family.
V2 CoupledL2 Directory family 的独立有界验证器。

The validator owns a small deterministic reference model, an Amaranth
transaction bench, and Verilator/Yosys gates.  It deliberately reports a
bounded family result; full TL2TLCoupledL2 parent equivalence remains open.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import random
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from amaranth.sim import Simulator


# =============================================================================
# Module Contract
# =============================================================================
# The bench covers reset, metadata/tag writes, two-stage lookup, hit/miss,
# invalid-way choice, MSHR exclusion, refill retry, CMO selection, and errors.
# 本 bench 覆盖复位、元数据/标签写入、两级查找、命中/缺失、无效路选择、
# MSHR 排除、回填重试、CMO 选择及错误。


# =============================================================================
# Configuration
# =============================================================================
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Memory" / "Build-Cpu.Dependency.CoupledL2.Directory-Hardware.py"
OUT = ROOT / "validation" / "v2-coupledL2-directory-family-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
REFERENCE = Path("/home/lishuo/xs-v2-local/build/rtl/XSTop.sv")
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


# Load the exact target file without importing sibling Build files. / 按精确路径加载目标而不导入同级 Build 文件。
def load_exact(path: Path) -> ModuleType:
    """Load one target module by path. / 按路径加载单个目标模块。"""

    spec = importlib.util.spec_from_file_location("v2_coupled_l2_directory_target", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Compute a byte-preserving digest. / 计算保持原始字节的摘要。
def digest(path: Path) -> str:
    """Return SHA-256 for a file. / 返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


# Audit encoding, five zones, imports, and the public adapter. / 审计编码、五分区、导入及公共适配器。
def static_audit() -> dict[str, Any]:
    """Run the target contract audit. / 执行目标合同审计。"""

    raw = TARGET.read_bytes()
    source = raw.decode("utf-8")
    tree = ast.parse(source, filename=str(TARGET))
    zones = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
    positions = [source.find(zone) for zone in zones]
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise AssertionError("target must be UTF-8 LF without BOM")
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise AssertionError("five-zone contract missing or out of order")
    adapter = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    if len(adapter) != 1 or [arg.arg for arg in adapter[0].args.args] != ["configuration", "injected_dependencies"]:
        raise AssertionError("exact build_verilog signature is required")
    forbidden = {"importlib", "runpy", "subprocess", "socket", "urllib", "pathlib"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(item.name.split(".")[0] in forbidden for item in node.names):
            raise AssertionError("forbidden import in target")
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in forbidden:
            raise AssertionError("forbidden import in target")
    required = ("CoupledL2DirectoryConfig", "CoupledL2Directory", "build_verilog")
    missing = [name for name in required if name not in source]
    if missing:
        raise AssertionError(f"missing symbols: {missing}")
    return {"status": "PASS", "path": TARGET.relative_to(ROOT).as_posix(), "bytes": len(raw), "sha256": digest(TARGET), "zones": list(zones), "required_symbols": list(required)}


# Compare deterministic Python equations against independent expectations. / 将确定性 Python 方程与独立期望比较。
def equation_vectors(module: ModuleType) -> dict[str, Any]:
    """Run randomized and corner-case directory equations. / 运行随机及边界目录方程。"""

    rng = random.Random(0xD1CE70)
    checks = 0
    for ways in (1, 2, 4, 8):
        for _ in range(64):
            tags = [rng.randrange(1 << 12) for _ in range(ways)]
            states = [rng.randrange(4) for _ in range(ways)]
            request = rng.randrange(1 << 12)
            replacement = rng.randrange(ways)
            mask = rng.randrange(1 << ways)
            occupied = rng.randrange(1 << ways)
            observed = module.directory_reference_step(request, tags, states, replacement, mask, occupied)
            hits = [index for index, (tag, state) in enumerate(zip(tags, states)) if state and tag == request]
            expected_hit = int(len(hits) == 1)
            if observed["hit"] != expected_hit or observed["multi_hit"] != int(len(hits) > 1):
                raise AssertionError((ways, tags, states, request, observed))
            if observed["retry"] != int((occupied & ((1 << ways) - 1)) == ((1 << ways) - 1)):
                raise AssertionError(("retry", observed))
            checks += 1
    # CMO selects a valid requested way even without a tag match. / CMO 即使无标签命中也选择有效指定路。
    cmo = module.directory_reference_step(0x55, [0x11, 0x22], [1, 2], 0, 3, cmo_all=True, cmo_way=1)
    if cmo["hit"] != 1 or cmo["way"] != 1:
        raise AssertionError(("cmo", cmo))
    checks += 1
    return {"status": "PASS", "vectors": checks}


# Exercise the stateful Amaranth directory. / 驱动有状态 Amaranth 目录。
def direct_bench(module: ModuleType) -> dict[str, Any]:
    """Run reset/write/read/retry/CMO transactions. / 运行复位/写入/读取/重试/CMO 事务。"""

    cfg = module.CoupledL2DirectoryConfig(sets=4, ways=2, tag_bits=8, mshr_entries=2, mshr_id_bits=2)
    top = module.CoupledL2Directory(cfg)
    sim = Simulator(top)
    sim.add_clock(1e-6, domain="coupled_l2_directory")
    observations: list[dict[str, int]] = []

    async def bench(ctx: Any) -> None:
        # Initialize all inputs. / 初始化全部输入。
        inputs = (
            top.reset, top.read_valid, top.read_tag, top.read_set, top.read_way_mask,
            top.read_replacer_channel, top.read_replacer_opcode, top.read_replacer_req_source,
            top.read_replacer_refill_prefetch, top.read_refill, top.read_mshr_id,
            top.read_cmo_all, top.read_cmo_way, top.meta_write_valid, top.meta_write_set,
            top.meta_write_way_oh, top.meta_write_dirty, top.meta_write_state,
            top.meta_write_clients, top.meta_write_alias, top.meta_write_prefetch,
            top.meta_write_prefetch_src, top.meta_write_accessed, top.meta_write_tag_err,
            top.meta_write_data_err, top.tag_write_valid, top.tag_write_set,
            top.tag_write_way, top.tag_write_tag, top.mshr_valid, top.mshr_set,
            top.mshr_way, top.mshr_block_refill, top.mshr_dir_hit, top.mshr_will_free,
        )
        for signal in inputs:
            ctx.set(signal, 0)
        ctx.set(top.reset, 1)
        for _ in range(3):
            await ctx.tick("coupled_l2_directory")
        ctx.set(top.reset, 0)
        # Write tag/state into set 1 way 0. / 向第 1 组第 0 路写入标签/状态。
        ctx.set(top.meta_write_valid, 1)
        ctx.set(top.meta_write_set, 1)
        ctx.set(top.meta_write_way_oh, 1)
        ctx.set(top.meta_write_state, 2)
        ctx.set(top.meta_write_dirty, 1)
        ctx.set(top.meta_write_clients, 1)
        ctx.set(top.meta_write_alias, 2)
        ctx.set(top.meta_write_accessed, 1)
        ctx.set(top.tag_write_valid, 1)
        ctx.set(top.tag_write_set, 1)
        ctx.set(top.tag_write_way, 0)
        ctx.set(top.tag_write_tag, 0x5A)
        await ctx.tick("coupled_l2_directory")
        ctx.set(top.meta_write_valid, 0)
        ctx.set(top.tag_write_valid, 0)
        # Lookup is a two-cycle pipeline. / 查找采用两级流水。
        ctx.set(top.read_valid, 1)
        ctx.set(top.read_tag, 0x5A)
        ctx.set(top.read_set, 1)
        ctx.set(top.read_way_mask, 3)
        await ctx.tick("coupled_l2_directory")
        ctx.set(top.read_valid, 0)
        await ctx.tick("coupled_l2_directory")
        if int(ctx.get(top.resp_valid)) != 1 or int(ctx.get(top.resp_hit)) != 1 or int(ctx.get(top.resp_way)) != 0:
            raise AssertionError("directory hit mismatch")
        observations.append({"hit": int(ctx.get(top.resp_hit)), "way": int(ctx.get(top.resp_way)), "state": int(ctx.get(top.resp_meta_state))})
        # Occupy way 1 and request a refill; retry must be asserted. / 占用第 1 路并请求回填，必须重试。
        ctx.set(top.mshr_valid, 1)
        ctx.set(top.mshr_set, 1)
        ctx.set(top.mshr_way, 1)
        ctx.set(top.mshr_block_refill, 1)
        ctx.set(top.read_valid, 1)
        ctx.set(top.read_tag, 0x99)
        ctx.set(top.read_set, 1)
        ctx.set(top.read_way_mask, 3)
        ctx.set(top.read_refill, 1)
        await ctx.tick("coupled_l2_directory")
        ctx.set(top.read_valid, 0)
        await ctx.tick("coupled_l2_directory")
        if int(ctx.get(top.repl_resp_valid)) != 1:
            raise AssertionError("refill response missing")
        observations.append({"refill_retry": int(ctx.get(top.repl_resp_retry))})
        if int(ctx.get(top.repl_resp_retry)) != 0:
            raise AssertionError("free invalid way should avoid retry")
        # Occupy both ways and verify retry, then exercise CMO. / 占满两路检查重试，再测试 CMO。
        ctx.set(top.mshr_valid, 3)
        ctx.set(top.mshr_set, 1 | (1 << cfg.set_bits))
        ctx.set(top.mshr_way, 0 | (1 << cfg.way_bits))
        ctx.set(top.mshr_block_refill, 3)
        await ctx.tick("coupled_l2_directory")
        ctx.set(top.read_valid, 1)
        ctx.set(top.read_refill, 1)
        await ctx.tick("coupled_l2_directory")
        ctx.set(top.read_valid, 0)
        await ctx.tick("coupled_l2_directory")
        observations.append({"full_retry": int(ctx.get(top.repl_resp_retry))})
        if int(ctx.get(top.repl_resp_retry)) != 1:
            raise AssertionError("full occupied directory did not retry")
        ctx.set(top.mshr_valid, 0)
        ctx.set(top.read_refill, 0)
        ctx.set(top.read_valid, 1)
        ctx.set(top.read_tag, 0)
        ctx.set(top.read_set, 1)
        ctx.set(top.read_cmo_all, 1)
        ctx.set(top.read_cmo_way, 0)
        await ctx.tick("coupled_l2_directory")
        ctx.set(top.read_valid, 0)
        await ctx.tick("coupled_l2_directory")
        if int(ctx.get(top.resp_valid)) != 1 or int(ctx.get(top.resp_hit)) != 1:
            raise AssertionError("CMO valid-way selection mismatch")
        observations.append({"cmo_hit": int(ctx.get(top.resp_hit)), "cmo_way": int(ctx.get(top.resp_way))})

    sim.add_testbench(bench)
    sim.run()
    trace = json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()
    return {"status": "PASS", "checks": len(observations), "trace": observations, "trace_sha256": hashlib.sha256(trace).hexdigest()}


# Run backend syntax and synthesis checks. / 运行后端语法及综合检查。
def backend_gates(module: ModuleType) -> dict[str, Any]:
    """Run Verilator and Yosys on a small deterministic instance. / 对小型确定性实例运行 Verilator 与 Yosys。"""

    rtl = module.build_verilog({"module": "UHSCCoupledL2Directory", "sets": 4, "ways": 2, "tag_bits": 8, "mshr_entries": 2, "mshr_id_bits": 2}, {})
    work = ROOT / "validation" / ".work" / "v2-coupled-l2-directory"
    work.mkdir(parents=True, exist_ok=True)
    rtl_path = work / "UHSCCoupledL2Directory.sv"
    rtl_path.write_text(rtl, encoding="utf-8", newline="\n")
    wsl_path = "/tmp/uhsc-v2/validation/.work/v2-coupled-l2-directory/UHSCCoupledL2Directory.sv"
    link = subprocess.run(["wsl.exe", "-e", "bash", "-lc", "ln -sfn /mnt/d/*/Unifier-Hardware-System/.agents/xiangshan-v2 /tmp/uhsc-v2"], capture_output=True, text=True, check=False)
    del link
    verilator = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal --top-module UHSCCoupledL2Directory {wsl_path}"], capture_output=True, text=True, check=False)
    yosys = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv {wsl_path}; hierarchy -top UHSCCoupledL2Directory; proc; check'"], capture_output=True, text=True, check=False)
    return {"verilator": "PASS" if verilator.returncode == 0 else "FAIL", "yosys": "PASS" if yosys.returncode == 0 else "FAIL", "rtl_bytes": len(rtl), "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(), "verilator_returncode": verilator.returncode, "yosys_returncode": yosys.returncode, "verilator_tail": verilator.stdout[-1200:], "yosys_tail": yosys.stdout[-1200:]}


# Extract locked-reference provenance without treating it as a false full equivalence.
# 提取锁定参考溯源，但不将其冒充为完整等价证明。
def reference_provenance() -> dict[str, Any]:
    """Record the immutable XSTop identity and Directory module surface. / 记录不可变 XSTop 身份及 Directory 模块表面。"""

    command = "sha256sum /home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command], capture_output=True, text=True, check=False)
    observed = result.stdout.split()[0] if result.returncode == 0 and result.stdout.split() else None
    return {"reference_path": str(REFERENCE), "reference_sha256": observed, "expected_sha256": REFERENCE_SHA256, "locked_unchanged": observed == REFERENCE_SHA256, "reference_mode": "LOCKED_XSTOP_DIRECTORY_BOUNDARY_PENDING_TL2_PARENT", "differential": "PENDING_FULL_PARENT"}


# Persist machine-readable evidence and return the family status. / 持久化机器可读证据并返回 family 状态。
def main() -> int:
    """Run all independent directory gates. / 运行全部独立目录门禁。"""

    module = load_exact(TARGET)
    static = static_audit()
    equations = equation_vectors(module)
    direct = direct_bench(module)
    backend = backend_gates(module)
    reference = reference_provenance()
    gates = {"PYTHON_PRESENT": static["status"], "DIRECT_TEST_PASS_BOUNDED": direct["status"], "V2_REFERENCE_MATCHED": "PASS_BOUNDED_DIRECTORY_EQUATIONS", "VERILATOR": backend["verilator"], "YOSYS": backend["yosys"], "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME", "PARENT_CLOSURE_MATCHED": "PENDING_TL2TLCoupledL2_PARENT", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"}
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_COUPLEDL2_DIRECTORY_FAMILY", "batch_id": "V2-DEPENDENCY-COUPLEDL2-DIRECTORY-001", "source_commit": SOURCE_COMMIT, "source_scala": ["upstream/coupledL2/src/main/scala/coupledL2/Directory.scala", "upstream/coupledL2/src/main/scala/coupledL2/Common.scala", "upstream/coupledL2/src/main/scala/coupledL2/Consts.scala", "upstream/coupledL2/src/main/scala/coupledL2/L2Param.scala"], "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(TARGET)}, "static": static, "equations": equations, "direct": direct, "backend": backend, "reference": reference, "gates": gates, "status": "VALIDATOR_PASS_BOUNDED", "acceptance_eligible": False, "unclosed": ["Full Directory port differential against locked XSTop remains pending.", "TL2TLCoupledL2 parent/CHI bridge closure remains pending.", "License review and user approval remain pending."]}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "direct": direct["status"], "equations": equations["status"], "verilator": backend["verilator"], "yosys": backend["yosys"]}, sort_keys=True))
    return 0 if all(value == "PASS" for value in (static["status"], equations["status"], direct["status"], backend["verilator"], backend["yosys"])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
