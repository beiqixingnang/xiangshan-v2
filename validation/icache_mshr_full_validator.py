"""Independent V2 ICacheMSHR family closure validator.
昆明湖 V2 ICacheMSHR 族独立闭环验证器。
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator


# Module Contract
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Icache.ICacheMshr-Hardware.py"
REF_FETCH = ROOT / "validation/reference-closures/ICacheMSHR.sv"
REF_PREFETCH = ROOT / "validation/reference-closures/ICacheMSHR_4.sv"
HARNESS = ROOT / "validation/icache_mshr_full_diff_tb.cpp"
WORK = ROOT / "validation/.work/v2-icache-mshr-full"
RESULT = ROOT / "validation/v2-icache-mshr-family-results.json"
CONTRACT = ROOT / "validation/v2-icache-mshr-family-contract-audit.json"
COVERAGE = ROOT / "validation/v2-icache-mshr-family-coverage-manifest.json"
MAPPING = ROOT / "validation/v2-icache-mshr-family-mapping-update.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED = {
    "path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
    "sha256": "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d",
}


# Configuration
# ---------------------------------------------------------------------------
def digest(path: Path) -> str:
    """Hash exact file bytes for reproducible evidence. / 对文件原始字节计算可复现摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_target() -> Any:
    """Load the final Build-Cpu target by exact path. / 按精确路径加载最终 Build-Cpu 目标。"""
    spec = importlib.util.spec_from_file_location("v2_icache_mshr_full_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def static_contract() -> dict[str, Any]:
    """Audit encoding, zones, adapter, and bilingual function comments.
    审计编码、分区、适配器及双语函数注释。
    """
    raw = TARGET.read_bytes()
    text = raw.decode("utf-8")
    tree = ast.parse(text, filename=str(TARGET))
    lines = text.splitlines()
    required = ["Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry"]
    positions = [text.find(marker) for marker in required]
    missing_comments: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            index = node.lineno - 2
            while index >= 0 and not lines[index].strip():
                index -= 1
            if index < 0 or not lines[index].lstrip().startswith("#") or "/" not in lines[index]:
                missing_comments.append(f"{node.name}:{node.lineno}")
    adapters = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    adapter_args = [arg.arg for arg in adapters[0].args.args] if len(adapters) == 1 else []
    result = {
        "utf8": True,
        "bom": raw.startswith(b"\xef\xbb\xbf"),
        "lf_only": b"\r" not in raw,
        "ast_parse": True,
        "five_zone_order": positions,
        "zones_ordered": all(position >= 0 for position in positions) and positions == sorted(positions),
        "adapter_args": adapter_args,
        "adapter_exact": adapter_args == ["configuration", "injected_dependencies"]
        and not adapters[0].args.vararg and not adapters[0].args.kwarg if len(adapters) == 1 else False,
        "missing_bilingual_comments": missing_comments,
        "path": TARGET.relative_to(ROOT).as_posix(),
        "bytes": len(raw),
        "sha256": digest(TARGET),
    }
    result["status"] = "PASS" if (
        not result["bom"] and result["lf_only"] and result["zones_ordered"]
        and result["adapter_exact"] and not missing_comments
    ) else "FAIL"
    return result


# Implementation
# ---------------------------------------------------------------------------
def xorshift(state: int) -> int:
    """Advance the deterministic direct-test generator. / 推进确定性的 direct 测试生成器。"""
    state &= 0xFFFFFFFF
    state ^= (state << 13) & 0xFFFFFFFF
    state ^= state >> 17
    state ^= (state << 5) & 0xFFFFFFFF
    return state & 0xFFFFFFFF


def direct_check(module: Any, is_fetch: bool) -> dict[str, Any]:
    """Exercise reset, allocation, lookup, issue, flush, and invalidation.
    覆盖复位、分配、查找、发出、flush 与失效路径。
    """
    dut = module.ICacheMSHR(entry_id=0 if is_fetch else 4, is_fetch=is_fetch)
    state = 0x9E3779B9
    events: list[dict[str, int]] = []
    for cycle in range(1024):
        state = xorshift(state)
        reset = int(cycle in (0, 511, 777))
        event = {
            "reset": reset,
            "fencei": int((state >> 0) & 1),
            # Fetch's parent ties this input low in Scala, but the candidate
            # boundary still exposes it for compatibility; drive both values
            # to prove that the fetch specialization ignores it.
            "flush": int((state >> 1) & 1),
            "wfi": int((state >> 2) & 1),
            "req": int((state >> 3) & 1),
            "blk": int((state >> 4) & ((1 << 42) - 1)),
            "set": int((state >> 10) & 0xFF),
            "lk0_blk": int((state >> 12) & ((1 << 42) - 1)),
            "lk0_set": int((state >> 18) & 0xFF),
            "lk1_blk": int((state >> 20) & ((1 << 42) - 1)),
            "lk1_set": int((state >> 26) & 0xFF),
            "acq_ready": int((state >> 27) & 1),
            "victim": int((state >> 28) & 3),
            "invalid": int((state >> 30) & 1),
        }
        if cycle % 43 == 0:
            event["fencei"] = 1
        if not is_fetch and cycle % 47 == 0:
            event["flush"] = 1
        if cycle % 61 == 0:
            event["req"] = 1
        if cycle % 79 == 0:
            event["wfi"] = 1
        if reset:
            event.update(reset=1, fencei=1, flush=int(not is_fetch), wfi=1, req=1)
        events.append(event)

    valid = flush_reg = fencei_reg = issue = 0
    blk = set_idx = way = latency = 0
    checks = 0

    async def bench(ctx: Any) -> None:
        nonlocal valid, flush_reg, fencei_reg, issue, blk, set_idx, way, latency, checks
        ctx.set(dut.reset, 1)
        ctx.set(dut.fencei, 1)
        ctx.set(dut.flush, 1)
        ctx.set(dut.wfi_req, 1)
        await ctx.delay(1e-9)
        if int(ctx.get(dut.req_ready)) != 0 or int(ctx.get(dut.wfi_safe)) != 1:
            raise AssertionError("asynchronous reset output")
        ctx.set(dut.reset, 0)
        for cycle, event in enumerate(events):
            ctx.set(dut.reset, event["reset"])
            ctx.set(dut.fencei, event["fencei"])
            ctx.set(dut.flush, event["flush"])
            ctx.set(dut.wfi_req, event["wfi"])
            ctx.set(dut.req_valid, event["req"])
            ctx.set(dut.req_blk_paddr, event["blk"])
            ctx.set(dut.req_v_set_idx, event["set"])
            ctx.set(dut.acquire_ready, event["acq_ready"])
            ctx.set(dut.victim_way, event["victim"])
            ctx.set(dut.invalid, event["invalid"])
            for index in range(2):
                ctx.set(dut.lookup_valid[index], (cycle + index) & 1)
                ctx.set(dut.lookup_blk_paddr[index], event[f"lk{index}_blk"])
                ctx.set(dut.lookup_v_set_idx[index], event[f"lk{index}_set"])
            await ctx.delay(1e-9)
            effective_flush = event["flush"] if not is_fetch else 0
            if event["reset"]:
                expected = {"req_ready": 0, "acquire_valid": 0, "lookup0": 0, "lookup1": 0, "info": 0, "wfi": 1}
            else:
                expected = {
                    "req_ready": int(not valid and not effective_flush and not event["fencei"]),
                    "acquire_valid": int(valid and not issue and not effective_flush and not event["fencei"] and not event["wfi"]),
                    "lookup0": int(valid and not fencei_reg and not flush_reg and event["lk0_blk"] == blk and event["lk0_set"] == set_idx),
                    "lookup1": int(valid and not fencei_reg and not flush_reg and event["lk1_blk"] == blk and event["lk1_set"] == set_idx),
                    "info": int(valid and not flush_reg and not fencei_reg),
                    "wfi": int(not (valid and issue)),
                }
            observed = {
                "req_ready": int(ctx.get(dut.req_ready)),
                "acquire_valid": int(ctx.get(dut.acquire_valid)),
                "lookup0": int(ctx.get(dut.lookup_hit[0])),
                "lookup1": int(ctx.get(dut.lookup_hit[1])),
                "info": int(ctx.get(dut.info_valid)),
                "wfi": int(ctx.get(dut.wfi_safe)),
            }
            if observed != expected:
                raise AssertionError(("cycle", cycle, observed, expected, event))
            expected_blk = 0 if event["reset"] else blk
            expected_set = 0 if event["reset"] else set_idx
            if int(ctx.get(dut.acquire_address)) != ((expected_blk << 6) & ((1 << 48) - 1)):
                raise AssertionError(("address", cycle))
            if int(ctx.get(dut.acquire_v_set_idx)) != expected_set:
                raise AssertionError(("set", cycle))
            expected_way = 0 if event["reset"] else way
            expected_source = (0 if is_fetch else 4) & ((1 << dut.cfg.source_bits) - 1)
            expected_alias = (expected_set >> (dut.cfg.idx_bits - dut.cfg.alias_tag_bits)) if dut.cfg.alias_tag_bits else 0
            if int(ctx.get(dut.acquire_opcode)) != 4:
                raise AssertionError(("opcode", cycle))
            if int(ctx.get(dut.acquire_size)) != dut.cfg.block_off_bits:
                raise AssertionError(("size", cycle))
            if int(ctx.get(dut.acquire_source)) != expected_source:
                raise AssertionError(("source", cycle))
            if int(ctx.get(dut.acquire_alias_tag)) != expected_alias:
                raise AssertionError(("alias", cycle))
            if int(ctx.get(dut.info_blk_paddr)) != expected_blk or int(ctx.get(dut.info_v_set_idx)) != expected_set or int(ctx.get(dut.info_way)) != expected_way:
                raise AssertionError(("response payload", cycle))
            expected_latency = 0 if event["reset"] else latency
            if int(ctx.get(dut.perf_latency)) != expected_latency:
                raise AssertionError(("latency", cycle))
            checks += 1
            req_fire = bool(event["req"] and expected["req_ready"])
            acquire_fire = bool(expected["acquire_valid"] and event["acq_ready"])
            if event["reset"]:
                valid = flush_reg = fencei_reg = issue = 0
                blk = set_idx = way = latency = 0
            else:
                if event["fencei"] or effective_flush:
                    fencei_reg = flush_reg = 1
                    if not issue:
                        valid = 0
                if req_fire:
                    valid = 1
                    flush_reg = fencei_reg = issue = 0
                    blk = event["blk"]
                    set_idx = event["set"]
                if valid and issue:
                    latency = (latency + 1) & 0xFFFF
                if acquire_fire:
                    issue = 1
                    way = event["victim"]
                    latency = 0
                if event["invalid"]:
                    valid = 0
            await ctx.tick("sync")
        if checks != len(events):
            raise AssertionError("incomplete direct trace")

    sim = Simulator(dut)
    sim.add_clock(1e-6, domain="sync")
    sim.add_testbench(bench)
    sim.run()
    return {
        "status": "PASS",
        "variant": "fetch-id0" if is_fetch else "prefetch-id4",
        "vectors": checks,
        "observation_points": ["async reset", "miss allocation", "lookup hit", "acquire backpressure", "flush", "invalid"],
    }


def wsl_path(path: Path) -> str:
    """Convert a local path to WSL syntax. / 将本地路径转换为 WSL 路径。"""
    absolute = path.resolve()
    drive = absolute.drive.rstrip(":").lower()
    if len(drive) == 1:
        return f"/mnt/{drive}/{absolute.as_posix().split(':', 1)[1].lstrip('/')}"
    completed = subprocess.run(["wsl.exe", "wslpath", "-a", str(absolute)], text=True, capture_output=True, check=True)
    return completed.stdout.strip()


def run_wsl(command: list[str], cwd: Path | None = None) -> dict[str, Any]:
    """Run one bounded WSL command and retain diagnostics. / 运行有界 WSL 命令并保存诊断。"""
    rendered = " ".join(shlex.quote(item) for item in command)
    if cwd is not None:
        rendered = f"cd {shlex.quote(wsl_path(cwd))} && {rendered}"
    completed = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered], text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    output = (completed.stdout or "") + (completed.stderr or "")
    return {
        "command": command,
        "returncode": completed.returncode,
        "result": "PASS" if completed.returncode == 0 else "FAIL",
        "output_tail": output[-2400:],
        "output_sha256": hashlib.sha256(output.encode("utf-8", "replace")).hexdigest(),
    }


def export_rtl(module: Any, variant: str) -> Path:
    """Export one deterministic target specialization. / 导出一个确定性的目标特化。"""
    WORK.mkdir(parents=True, exist_ok=True)
    config = {"entry_id": 0 if variant == "fetch" else 4, "is_fetch": variant == "fetch"}
    path = WORK / f"ICacheMSHR-{variant}-target.sv"
    path.write_text(module.build_verilog(config, None), encoding="utf-8", newline="\n")
    return path


def adapter_smoke(module: Any) -> dict[str, Any]:
    """Check deterministic exact-path adapter exports. / 检查精确路径适配器的确定性导出。"""
    outputs = {}
    for variant, config in (("fetch-id0", {"entry_id": 0, "is_fetch": True}),
                            ("prefetch-id4", {"entry_id": 4, "is_fetch": False})):
        first = module.build_verilog(config, None)
        second = module.build_verilog(config, None)
        first_bytes = first.encode("utf-8")
        second_bytes = second.encode("utf-8")
        outputs[variant] = {
            "nonempty": bool(first_bytes),
            "deterministic": first_bytes == second_bytes,
            "sha256": hashlib.sha256(first_bytes).hexdigest(),
            "bytes": len(first_bytes),
            "top_declared": "module ICacheMSHR" in first,
        }
    return {"status": "PASS" if all(item["nonempty"] and item["deterministic"] and item["top_declared"] for item in outputs.values()) else "FAIL", "variants": outputs}


def py_compile_gate() -> dict[str, Any]:
    """Run Python bytecode compilation on the target and validator. / 对目标与验证器执行 Python 编译门禁。"""
    completed = subprocess.run([sys.executable, "-m", "py_compile", str(TARGET), str(Path(__file__))], text=True, capture_output=True, check=False)
    return {"status": "PASS" if completed.returncode == 0 else "FAIL", "returncode": completed.returncode, "stderr_sha256": hashlib.sha256((completed.stderr or "").encode()).hexdigest()}


def trace(source: Path, top: str, defines: list[str], name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build and run the independent C++ trace harness. / 构建并运行独立 C++ 轨迹测试台。"""
    obj = WORK / f"obj-{name}"
    out = WORK / f"{name}.jsonl"
    if obj.exists():
        shutil.rmtree(obj)
    obj.mkdir(parents=True, exist_ok=True)
    flags = " ".join(f"-D{item}" for item in defines)
    command = ["verilator", "--cc", "--exe", "--build", "--Wno-fatal", "--top-module", top,
               "--Mdir", wsl_path(obj), wsl_path(source), wsl_path(HARNESS)]
    if flags:
        command.extend(["-CFLAGS", flags])
    build = run_wsl(command)
    run: dict[str, Any] | None = None
    if build["returncode"] == 0:
        binary = obj / f"V{top}"
        run = run_wsl([wsl_path(binary)])
        rendered = f"cd {shlex.quote(wsl_path(obj))} && ./V{top} > {shlex.quote(wsl_path(out))}"
        full = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered], text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
        run["full_returncode"] = full.returncode
        run["full_output_sha256"] = hashlib.sha256((full.stdout or "").encode()).hexdigest()
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()] if out.is_file() else []
    return {
        "build": build,
        "run": run,
        "trace": {"path": out.relative_to(ROOT).as_posix(), "sha256": digest(out) if out.is_file() else None, "vectors": len(rows)},
    }, rows


def backend_gate(path: Path, top: str) -> dict[str, Any]:
    """Run target Verilator and Yosys checks. / 运行目标 Verilator 与 Yosys 检查。"""
    source = wsl_path(path)
    verilator = run_wsl(["verilator", "--lint-only", "--Wno-fatal", "--top-module", top, source])
    yosys = run_wsl(["yosys", "-p", f"read_verilog -sv {source}; hierarchy -top {top}; proc; check"])
    return {"verilator": verilator, "yosys": yosys}


def compare(name: str, target_rows: list[dict[str, Any]], reference_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare complete JSONL traces and identify the first mismatch.
    比较完整 JSONL 轨迹并定位首个差异。
    """
    equal = target_rows == reference_rows
    mismatch = None
    for index, (left, right) in enumerate(zip(target_rows, reference_rows)):
        if left != right:
            mismatch = {"index": index, "target": left, "reference": right}
            break
    if mismatch is None and len(target_rows) != len(reference_rows):
        mismatch = {"index": min(len(target_rows), len(reference_rows)), "target_length": len(target_rows), "reference_length": len(reference_rows)}
    target_blob = json.dumps(target_rows, sort_keys=True, separators=(",", ":")).encode()
    reference_blob = json.dumps(reference_rows, sort_keys=True, separators=(",", ":")).encode()
    return {
        "name": name,
        "comparison": "PASS" if equal else "FAIL",
        "behavioral_equivalence": equal,
        "target_vectors": len(target_rows),
        "reference_vectors": len(reference_rows),
        "target_trace_sha256": hashlib.sha256(target_blob).hexdigest(),
        "reference_trace_sha256": hashlib.sha256(reference_blob).hexdigest(),
        "first_mismatch": mismatch,
    }


# Public Adapter
# ---------------------------------------------------------------------------
def main() -> int:
    """Run all ICacheMSHR gates and write machine-readable evidence.
    运行全部 ICacheMSHR 门禁并写入机器可读证据。
    """
    module = load_target()
    contract = static_contract()
    compile_gate = py_compile_gate()
    smoke = adapter_smoke(module)
    direct = [direct_check(module, True), direct_check(module, False)]
    fetch_target = export_rtl(module, "fetch")
    prefetch_target = export_rtl(module, "prefetch")
    fetch_target_trace, fetch_target_rows = trace(fetch_target, "ICacheMSHR", ["TARGET"], "target-fetch")
    fetch_reference_trace, fetch_reference_rows = trace(REF_FETCH, "ICacheMSHR", [], "reference-fetch")
    prefetch_target_trace, prefetch_target_rows = trace(prefetch_target, "ICacheMSHR", ["TARGET", "PREFETCH"], "target-prefetch")
    prefetch_reference_trace, prefetch_reference_rows = trace(REF_PREFETCH, "ICacheMSHR_4", ["PREFETCH"], "reference-prefetch")
    comparisons = [
        compare("fetch-id0", fetch_target_rows, fetch_reference_rows),
        compare("prefetch-id4", prefetch_target_rows, prefetch_reference_rows),
    ]
    target_backend = {
        "fetch-id0": backend_gate(fetch_target, "ICacheMSHR"),
        "prefetch-id4": backend_gate(prefetch_target, "ICacheMSHR"),
    }
    reference_backend = {
        "fetch-id0": backend_gate(REF_FETCH, "ICacheMSHR"),
        "prefetch-id4": backend_gate(REF_PREFETCH, "ICacheMSHR_4"),
    }
    naming_path = ROOT / "UHSC-Naming-Manifest.json"
    naming = {
        "manifest": naming_path.relative_to(ROOT).as_posix(),
        "sha256": digest(naming_path) if naming_path.is_file() else None,
        "status": "NO_PROJECT_FACING_RENAME",
        "locked_reference_names_unchanged": True,
        "entries": [],
    }
    CONTRACT.write_text(json.dumps({
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_ICACHE_MSHR_CONTRACT_AUDIT",
        "batch_id": "V2-SEMANTIC-FRONTEND-ICACHE-MSHR",
        "source_commit": SOURCE_COMMIT,
        "target": contract,
        "py_compile": compile_gate,
        "adapter_smoke": smoke,
        "result": contract["status"],
        "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    COVERAGE.write_text(json.dumps({
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_ICACHE_MSHR_CHILD_COVERAGE",
        "batch_id": "V2-SEMANTIC-FRONTEND-ICACHE-MSHR",
        "source_commit": SOURCE_COMMIT,
        "closure_root": "core.frontend.icache.mshr",
        "children": [{
            "name": "ICacheMSHR",
            "source": "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala",
            "target": TARGET.relative_to(ROOT).as_posix(),
            "references": ["ICacheMSHR", "ICacheMSHR_4"],
            "variants": ["fetch-id0", "prefetch-id4"],
            "observation_points": ["async reset", "miss allocation", "lookup hit", "acquire valid/ready", "victim way", "response valid", "flush/fencei", "invalidation", "WFI safety"],
        }],
        "py_compile": compile_gate["status"],
        "adapter_smoke": smoke["status"],
        "direct": "PASS_BOUNDED_DIRECT" if all(item["status"] == "PASS" for item in direct) else "FAIL",
        "locked_sv_differential": "PASS_BOUNDED" if all(row["behavioral_equivalence"] for row in comparisons) else "FAIL",
        "verilator_target": "PASS" if all(item["verilator"]["result"] == "PASS" for item in target_backend.values()) else "FAIL",
        "yosys_target": "PASS" if all(item["yosys"]["result"] == "PASS" for item in target_backend.values()) else "FAIL",
        "parent_closure": "PENDING_FRONTEND_ICACHE_PARENT",
        "license_review": "PENDING_COORDINATOR_REVIEW",
        "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    MAPPING.write_text(json.dumps({
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_ICACHE_MSHR_MAPPING_UPDATE",
        "batch_id": "V2-SEMANTIC-FRONTEND-ICACHE-MSHR",
        "source_commit": SOURCE_COMMIT,
        "entries": [{
            "source": "ICacheMSHR(edge, isFetch, ID)",
            "source_path": "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala",
            "target": TARGET.relative_to(ROOT).as_posix(),
            "classification": "REWRITTEN_FAMILY",
            "covered_specializations": ["fetch-id0", "prefetch-id4"],
            "status": "DIFFERENTIAL_MATCHED" if all(row["behavioral_equivalence"] for row in comparisons) else "PENDING",
        }],
        "localization": naming,
        "gates": {"direct": "PASS_BOUNDED_DIRECT", "reference": "PASS_BOUNDED" if all(row["behavioral_equivalence"] for row in comparisons) else "FAIL", "parent_closure": "PENDING", "license": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
        "acceptance_eligible": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_ICACHE_MSHR_FAMILY",
        "batch_id": "V2-SEMANTIC-FRONTEND-ICACHE-MSHR",
        "source_commit": SOURCE_COMMIT,
        "locked_reference": LOCKED,
        "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(TARGET)},
        "source": {"path": "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala", "sha256": digest(ROOT / "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala")},
        "contract": contract,
        "py_compile": compile_gate,
        "adapter_smoke": smoke,
        "direct": direct,
        "comparisons": comparisons,
        "target_backend": target_backend,
        "reference_backend": reference_backend,
        "trace_artifacts": {"fetch_target": fetch_target_trace, "fetch_reference": fetch_reference_trace, "prefetch_target": prefetch_target_trace, "prefetch_reference": prefetch_reference_trace},
        "uhsc_localization": naming,
        "parent_closure": "PENDING_FRONTEND_ICACHE_PARENT",
        "license_gate": "PENDING_REVIEW",
        "status": "VALIDATOR_PASS_BOUNDED" if compile_gate["status"] == "PASS" and smoke["status"] == "PASS" and contract["status"] == "PASS" and all(item["status"] == "PASS" for item in direct) and all(row["behavioral_equivalence"] for row in comparisons) and all(item["verilator"]["result"] == "PASS" and item["yosys"]["result"] == "PASS" for item in target_backend.values()) else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "gates": {"ACCEPTED": "NOT_ALLOWED", "parent_closure": "PENDING", "license": "PENDING"},
        "notes": "Reference Yosys is recorded verbatim; generated Chisel references use automatic logic unsupported by the installed Yosys frontend. This does not alter or normalize the locked reference.",
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "direct_vectors": sum(item["vectors"] for item in direct), "comparisons": len(comparisons), "equivalent": all(row["behavioral_equivalence"] for row in comparisons), "target_backend": target_backend}, sort_keys=True))
    return 0 if payload["status"] == "VALIDATOR_PASS_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
