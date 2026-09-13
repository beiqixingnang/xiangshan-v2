"""Run direct V2 vector-family checks and structural audits.
执行 V2 向量族直接检查与结构审计。
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import inspect
import json
import py_compile
import random
import sys
from pathlib import Path
from typing import Any, Callable

from amaranth.sim import Simulator


ROOT = Path(__file__).resolve().parents[1]
TARGET_ROOT = ROOT / "python" / "ported" / "backend" / "fu" / "vector"
RESULT = ROOT / "validation" / "v2-vector-batch-direct-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
TARGETS = {
    "ByteMaskTailGen": TARGET_ROOT / "ByteMaskTailGen-Hardware.py",
    "DstMgu": TARGET_ROOT / "DstMgu-Hardware.py",
    "Mgtu": TARGET_ROOT / "Mgtu-Hardware.py",
    "NewMgu": TARGET_ROOT / "NewMgu-Hardware.py",
    "MaskExtrator": TARGET_ROOT / "utils" / "MaskExtrator-Hardware.py",
    "ScalaDupToVector": TARGET_ROOT / "utils" / "ScalaDupToVector-Hardware.py",
    "UIntToCont0s": TARGET_ROOT / "utils" / "UIntToCont0s-Hardware.py",
    "UIntToCont1s": TARGET_ROOT / "utils" / "UIntToCont1s-Hardware.py",
    "VecDataSplitModule": TARGET_ROOT / "utils" / "VecDataSplitModule-Hardware.py",
}


# Return a SHA-256 digest over exact bytes. / 对原始字节计算 SHA-256 摘要。
def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Load one target by exact path without package discovery. / 按精确路径加载目标，不进行包发现。
def load_target(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Audit the five zones, imports, and bilingual definition comments.
# 审计五个区域、导入边界及双语定义注释。
def audit_target(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    source = raw.decode("utf-8")
    tree = ast.parse(source, filename=str(path))
    lines = source.splitlines()
    zones = ("Module Contract", "Configuration", "Implementation",
             "Public Adapter", "Direct Entry")
    positions = [source.find(zone) for zone in zones]
    comment_errors: list[str] = []
    forbidden: list[str] = []
    blocked_roots = {"importlib", "runpy", "subprocess", "socket", "urllib",
                     "pathlib"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            previous = lines[node.lineno - 2].strip() if node.lineno > 1 else ""
            if not (previous.startswith("#") and "/" in previous):
                comment_errors.append(f"{node.name}:{node.lineno}")
        elif isinstance(node, ast.Import):
            forbidden.extend(item.name for item in node.names
                             if item.name.split(".")[0] in blocked_roots)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in blocked_roots:
                forbidden.append(node.module)
    adapters = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    adapter_args = ([arg.arg for arg in adapters[0].args.args]
                    if len(adapters) == 1 else [])
    doc = ast.get_docstring(tree, clean=False) or ""
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": len(raw),
        "sha256": digest(path),
        "utf8": True,
        "bom": raw.startswith(b"\xef\xbb\xbf"),
        "lf_only": b"\r" not in raw,
        "ast": True,
        "bilingual_docstring": bool(doc and any("a" <= c.lower() <= "z" for c in doc)
                                    and any("\u4e00" <= c <= "\u9fff" for c in doc)),
        "zones": positions == sorted(positions) and all(item >= 0 for item in positions),
        "adapter_args": adapter_args,
        "adapter_exact": adapter_args == ["configuration", "injected_dependencies"],
        "function_comment_errors": comment_errors,
        "forbidden_imports": forbidden,
        "explicit_all": "__all__" in source,
    }


# Simulate a combinational module over assignment vectors. / 对组合模块执行向量仿真。
def simulate_vectors(top: Any, assignments: list[list[tuple[Any, int]]], outputs: list[Any]) -> list[tuple[int, ...]]:
    observed: list[tuple[int, ...]] = []

    async def bench(ctx: Any) -> None:
        for values in assignments:
            for signal, value in values:
                ctx.set(signal, value)
            await ctx.delay(1e-9)
            observed.append(tuple(int(ctx.get(signal)) for signal in outputs))

    simulator = Simulator(top)
    simulator.add_testbench(bench)
    simulator.run()
    return observed


# Hash a JSON-serializable trace in canonical form. / 以规范形式哈希 JSON 轨迹。
def trace_hash(rows: Any) -> str:
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


# Exercise both contiguous-one and high-level boundary values. / 检查连续一掩码边界值。
def test_contiguous_ones(module: Any) -> dict[str, Any]:
    config = module.UIntToContConfig(uintWidth=3)
    top = module.UIntToContLow1s(config)
    assignments = [[(top.dataIn, value)] for value in range(8)]
    observed = simulate_vectors(top, assignments, [top.dataOut])
    expected = [((1 << value) - 1,) for value in range(8)]
    if observed != expected:
        raise AssertionError((observed, expected))
    return {"vectors": len(assignments), "boundary_values": [0, 1, 7],
            "trace_sha256": trace_hash(observed)}


# Exercise contiguous-zero mask boundaries. / 检查连续零掩码边界值。
def test_contiguous_zeros(module: Any) -> dict[str, Any]:
    config = module.UIntToContConfig(uintWidth=3)
    top = module.UIntToContLow0s(config)
    assignments = [[(top.dataIn, value)] for value in range(8)]
    observed = simulate_vectors(top, assignments, [top.dataOut])
    expected = [(((1 << 7) - 1) ^ ((1 << value) - 1),) for value in range(8)]
    if observed != expected:
        raise AssertionError((observed, expected))
    return {"vectors": len(assignments), "boundary_values": [0, 1, 7],
            "trace_sha256": trace_hash(observed)}


# Exercise all V2 mask expansion encodings and byte patterns. / 检查所有 V2 掩码展开编码与字节模式。
def test_mask(module: Any) -> dict[str, Any]:
    top = module.MaskExtractor(module.MaskExtractorConfig())
    assignments = [[(top.in_mask, value), (top.in_vsew, sew)]
                   for sew in range(4) for value in range(256)]
    observed = simulate_vectors(top, assignments, [top.out_mask])
    expected = []
    for sew in range(4):
        for value in range(256):
            expanded = sum(((value >> (index >> sew)) & 1) << index
                           for index in range(16))
            expected.append((expanded,))
    if observed != expected:
        raise AssertionError("MaskExtractor mismatch")
    return {"vectors": len(assignments), "sew_values": [0, 1, 2, 3],
            "trace_sha256": trace_hash(observed)}


# Exercise scalar duplication at every V2 element width. / 检查每种 V2 元素宽度的标量复制。
def test_scalar(module: Any) -> dict[str, Any]:
    top = module.ScalaDupToVector(module.ScalaDupToVectorConfig())
    scalars = [0, 1, 0x0123456789ABCDEF, 0xFEDCBA9876543210,
               0xFFFFFFFFFFFFFFFF, 0x8000000000000001]
    assignments = [[(top.in_scalaData, value), (top.in_vsew, sew)]
                   for sew in range(4) for value in scalars]
    observed = simulate_vectors(top, assignments, [top.out_vecData])
    expected = []
    for sew in range(4):
        width = (8, 16, 32, 64)[sew]
        for value in scalars:
            element = value & ((1 << width) - 1)
            packed = sum(element << (width * index)
                         for index in range(128 // width))
            expected.append((packed,))
    if observed != expected:
        raise AssertionError("ScalaDupToVector mismatch")
    return {"vectors": len(assignments), "trace_sha256": trace_hash(observed)}


# Exercise all packed splitter views with deterministic data. / 用确定性数据检查所有打包分割视图。
def test_split(module: Any) -> dict[str, Any]:
    top = module.VecDataSplitModule(module.VecDataSplitConfig())
    values = [(index * 0x9E3779B97F4A7C15) ^ 0x0123456789ABCDEF
              for index in range(256)]
    rows: list[dict[str, int]] = []
    assignments = [[(top.inVecData, value)] for value in values]
    outputs = top.outVec8b + top.outVec16b + top.outVec32b + top.outVec64b
    observed = simulate_vectors(top, assignments, outputs)
    for value, row in zip(values, observed):
        expected = tuple((value >> (width * index)) & ((1 << width) - 1)
                         for width, count in ((8, 16), (16, 8), (32, 4), (64, 2))
                         for index in range(count))
        if row != expected:
            raise AssertionError((value, row, expected))
        rows.append({"input": value, "out8_0": row[0], "out16_0": row[16],
                     "out32_0": row[24], "out64_0": row[28]})
    return {"vectors": len(values), "trace_sha256": trace_hash(rows)}


# Exercise mask-tail fill at VL boundaries and alternating data. / 检查 VL 边界与交替数据的掩码尾填充。
def test_mgtu(module: Any) -> dict[str, Any]:
    top = module.Mgtu(module.MgtuConfig())
    data = [0, (1 << 128) - 1, 0x0123456789ABCDEF0123456789ABCDEF,
            0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA]
    assignments = [[(top.in_vd, value), (top.in_vl, vl)]
                   for value in data for vl in range(256)]
    observed = simulate_vectors(top, assignments, [top.out_vd])
    expected = []
    for value in data:
        for vl in range(256):
            keep = (1 << min(vl, 128)) - 1
            expected.append(((value & keep) | (((1 << 128) - 1) & ~keep),))
    if observed != expected:
        raise AssertionError("Mgtu mismatch")
    return {"vectors": len(assignments), "vl_boundaries": [0, 1, 127, 128, 255],
            "trace_sha256": trace_hash(observed)}


# Exercise ByteMaskTailGen deterministic corners and pseudo-random vectors.
# 检查 ByteMaskTailGen 确定性边界与伪随机向量。
def test_byte(module: Any) -> dict[str, Any]:
    top = module.ByteMaskTailGen(module.ByteMaskTailGenConfig())
    rng = random.Random(0xB17E)
    vectors = [
        (0, 0, 0, 0, 0, 0, 0),
        (0, 16, 0, 0, 0, 0xFFFF, 0),
        (2, 7, 0, 0, 0, 0x5555, 0),
        (2, 7, 1, 1, 1, 0x00FF, 1),
        (7, 2, 1, 1, 3, 0xAAAA, 7),
    ]
    vectors.extend(tuple(rng.randrange(limit) for limit in (256, 256, 2, 2, 4, 65536, 8))
                   for _ in range(4096))
    signals = [top.in_begin, top.in_end, top.in_vma, top.in_vta,
               top.in_vsew, top.in_maskUsed, top.in_vdIdx]
    assignments = [[(signal, value) for signal, value in zip(signals, vector)]
                   for vector in vectors]
    observed = simulate_vectors(top, assignments, [top.out_activeEn, top.out_agnosticEn])
    expected = [module.byte_mask_model(*vector) for vector in vectors]
    if observed != expected:
        raise AssertionError("ByteMaskTailGen mismatch")
    return {"vectors": len(vectors), "corner_vectors": 5,
            "trace_sha256": trace_hash(observed)}


# Exercise the integrated V2 NewMgu mask-generation closure. / 检查集成 V2 NewMgu 掩码生成闭包。
def test_new_mgu(module: Any) -> dict[str, Any]:
    top = module.NewMgu(module.NewMguConfig())
    rng = random.Random(0x4D47)
    vectors = []
    for _ in range(4096):
        vectors.append((rng.getrandbits(128), rng.randrange(2), rng.randrange(2),
                        rng.randrange(256), rng.randrange(256), rng.randrange(4),
                        rng.randrange(4), rng.randrange(8), rng.randrange(2)))
    signals = [top.in_mask, top.in_info_ta, top.in_info_ma, top.in_info_vstart,
               top.in_info_vl, top.in_info_eew, top.in_info_vsew,
               top.in_info_vdIdx, top.in_isIndexedVls]
    assignments = [[(signal, value) for signal, value in zip(signals, vector)]
                   for vector in vectors]
    observed = simulate_vectors(top, assignments, [top.out_activeEn, top.out_agnosticEn])
    expected = [module.new_mgu_model(*vector) for vector in vectors]
    if observed != expected:
        raise AssertionError("NewMgu mismatch")
    return {"vectors": len(vectors), "indexed_modes": [0, 1],
            "trace_sha256": trace_hash(observed)}


# Exercise the folded V2 destination-mask merge closure. / 检查折叠的 V2 目的掩码合并闭包。
def test_dst_mgu(module: Any) -> dict[str, Any]:
    top = module.DstMgu(module.DstMguConfig())
    rng = random.Random(0xD57)
    vectors = [(rng.getrandbits(128), rng.getrandbits(128), rng.getrandbits(128),
                rng.randrange(2), rng.randrange(4), rng.randrange(8))
               for _ in range(4096)]
    signals = [top.in_vd, top.in_oldVd, top.in_mask, top.in_info_ma,
               top.in_info_eew, top.in_info_vdIdx]
    assignments = [[(signal, value) for signal, value in zip(signals, vector)]
                   for vector in vectors]
    observed = simulate_vectors(top, assignments, [top.out_vd])
    expected = [(module.dst_mgu_model(*vector),) for vector in vectors]
    if observed != expected:
        raise AssertionError("DstMgu mismatch")
    return {"vectors": len(vectors), "eew_modes": [0, 1, 2, 3],
            "trace_sha256": trace_hash(observed)}


# Run direct checks, exact-path imports, and deterministic adapter exports.
# 执行直接检查、精确路径导入及确定性适配器导出。
def main() -> int:
    audit_rows: dict[str, Any] = {}
    modules: dict[str, Any] = {}
    for index, (name, path) in enumerate(TARGETS.items()):
        audit_rows[name] = audit_target(path)
        py_compile.compile(str(path), doraise=True)
        modules[name] = load_target(path, f"v2_vector_direct_{index}")

    tests: dict[str, Any] = {
        "ByteMaskTailGen": test_byte(modules["ByteMaskTailGen"]),
        "DstMgu": test_dst_mgu(modules["DstMgu"]),
        "Mgtu": test_mgtu(modules["Mgtu"]),
        "NewMgu": test_new_mgu(modules["NewMgu"]),
        "MaskExtrator": test_mask(modules["MaskExtrator"]),
        "ScalaDupToVector": test_scalar(modules["ScalaDupToVector"]),
        "UIntToCont0s": test_contiguous_zeros(modules["UIntToCont0s"]),
        "UIntToCont1s": test_contiguous_ones(modules["UIntToCont1s"]),
        "VecDataSplitModule": test_split(modules["VecDataSplitModule"]),
    }
    adapters: dict[str, Any] = {}
    for name, module in modules.items():
        builder = module.build_verilog
        if list(inspect.signature(builder).parameters) != ["configuration", "injected_dependencies"]:
            raise AssertionError(f"adapter signature: {name}")
        first = builder(None, {})
        second = builder(None, {})
        if not isinstance(first, str) or not first.strip() or first != second:
            raise AssertionError(f"non-deterministic adapter: {name}")
        adapters[name] = {"bytes": len(first.encode()),
                          "sha256": hashlib.sha256(first.encode()).hexdigest(),
                          "contains_module": f"module {name if name != 'MaskExtrator' else 'MaskExtractor'}" in first
                          or name in ("UIntToCont0s", "UIntToCont1s")}
    contract_pass = all(row["utf8"] and not row["bom"] and row["lf_only"]
                        and row["ast"] and row["bilingual_docstring"] and row["zones"]
                        and row["adapter_exact"] and not row["function_comment_errors"]
                        and not row["forbidden_imports"] and row["explicit_all"]
                        for row in audit_rows.values())
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_VECTOR_BATCH_DIRECT_TESTS",
        "batch_id": "V2-P1-E-VECTOR-MASK",
        "source_commit": SOURCE_COMMIT,
        "source_authority": "canonical V2 Scala under upstream/src/main/scala",
        "status": "PASS_BOUNDED" if contract_pass else "FAIL",
        "targets": tests,
        "adapters": adapters,
        "contract_audit": {"status": "PASS" if contract_pass else "FAIL", "rows": audit_rows},
        "gates": {
            "PYTHON_PRESENT": "PASS",
            "DIRECT_TEST_PASS_BOUNDED": "PASS" if contract_pass else "FAIL",
            "V2_REFERENCE_MATCHED": "PENDING_DIFFERENTIAL_RUN",
            "PARENT_CLOSURE": "PENDING_DIFFERENTIAL_RUN",
            "VERILATOR": "PENDING_DIFFERENTIAL_RUN",
            "YOSYS": "PENDING_DIFFERENTIAL_RUN",
            "UHSC_LOCALIZED": "PENDING_EXTERNAL_WRAPPER",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "acceptance_eligible": False,
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8", newline="\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if contract_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
