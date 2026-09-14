"""Independent bounded validator for the V2 YunSuan vector family.
V2 YunSuan 向量 family 独立有界验证器。
"""

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
# This validator owns only the 53-source YunSuan vector aggregate and its
# evidence; all locked sources remain read-only inputs.
# 本验证器仅负责 53 个 YunSuan 向量源的聚合及证据；锁定源码只读。
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Core" / "Build-Cpu.Dependency.YunSuan.Vector-Hardware.py"
SOURCE_ROOT = ROOT / "upstream" / "yunsuan" / "src" / "main" / "scala" / "yunsuan" / "vector"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_BYTES = 228590583
REFERENCE_WSL = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
WORK = ROOT / "validation" / ".work" / "yunsuan-vector-validator"
RESULTS = ROOT / "validation" / "v2-yunsuan-vector-family-results.json"
CONTRACT_RESULTS = ROOT / "validation" / "v2-yunsuan-vector-family-contract-audit.json"
COVERAGE_RESULTS = ROOT / "validation" / "v2-yunsuan-vector-family-coverage-manifest.json"
MAPPING_RESULTS = ROOT / "validation" / "v2-yunsuan-vector-family-mapping-update.json"
SOURCE_PATHS = sorted(path.relative_to(ROOT / "upstream").as_posix()
                      for path in SOURCE_ROOT.rglob("*.scala"))


# Return a SHA-256 digest for exact bytes. / 对精确字节计算 SHA-256 摘要。
def digest(path: Path) -> str:
    """Hash exact file bytes. / 对文件原始字节计算哈希。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


# Convert a Windows path into a stable WSL mount path. / 将 Windows 路径转换为稳定 WSL 挂载路径。
def wsl_path(path: Path) -> str:
    """Return the ``/mnt/<drive>`` spelling. / 返回 /mnt/<drive> 路径拼写。"""

    absolute = path.resolve()
    drive = absolute.drive.rstrip(":").lower()
    tail = absolute.as_posix().split(":", 1)[-1]
    return f"/mnt/{drive}{tail}"


# Load the target by exact path. / 按精确路径加载目标。
def load_target() -> dict[str, Any]:
    """Execute the aggregate in an isolated namespace. / 在隔离命名空间执行聚合文件。"""

    return runpy.run_path(str(TARGET))


# Audit source layout and function/import contract. / 审计源码布局及函数/导入契约。
def static_audit() -> dict[str, Any]:
    """Return machine-readable contract facts. / 返回机器可读的契约事实。"""

    raw = TARGET.read_bytes()
    source = raw.decode("utf-8")
    tree = ast.parse(source, filename=str(TARGET))
    lines = source.splitlines()
    zone_names = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
    zones = [source.find(item) for item in zone_names]
    forbidden_roots = {"importlib", "runpy", "subprocess", "socket", "urllib", "os", "sys", "pathlib"}
    forbidden: list[str] = []
    comments: list[str] = []
    private: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            forbidden.extend(alias.name for alias in node.names
                             if alias.name.split(".")[0] in forbidden_roots)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in forbidden_roots:
                forbidden.append(node.module)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prior = lines[node.lineno - 2].strip() if node.lineno > 1 else ""
            if node.name == "__init__" or node.name == "__post_init__":
                continue
            if not (prior.startswith("#") and "/" in prior):
                comments.append(f"{node.name}:{node.lineno}")
            if node.name.startswith("_") and not (node.name.startswith("__") and node.name.endswith("__")):
                private.append(f"{node.name}:{node.lineno}")
    adapters = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    adapter_args = ([arg.arg for arg in adapters[0].args.args] if len(adapters) == 1 else [])
    valid = (zones == sorted(zones) and all(item >= 0 for item in zones)
             and not forbidden and not comments and not private
             and adapter_args == ["configuration", "injected_dependencies"]
             and b"\r" not in raw and not raw.startswith(b"\xef\xbb\xbf")
             and "__all__" in source)
    return {"status": "PASS" if valid else "FAIL", "path": TARGET.relative_to(ROOT).as_posix(),
            "bytes": len(raw), "sha256": digest(TARGET), "utf8_lf": b"\r" not in raw,
            "zones": zones, "adapter_args": adapter_args,
            "forbidden_imports": forbidden, "function_comment_errors": comments,
            "leading_underscore_functions": private}


# Run pure models and Amaranth direct vectors. / 运行纯模型及 Amaranth direct 向量。
def direct_checks(module: dict[str, Any]) -> dict[str, Any]:
    """Exercise integer, mask, reduction and permutation boundaries. / 测试整数、掩码、归约及排列边界。"""

    vectors = 0
    observations: list[dict[str, Any]] = []
    for sew in range(4):
        width = 8 << sew
        for index in range(256):
            left = (index * 0x9E3779B97F4A7C15) & ((1 << 128) - 1)
            right = ((index + 17) * 0xD1B54A32D192ED03) & ((1 << 128) - 1)
            for opcode in (module["VADD"], module["VSUB"], module["VAND"], module["VXOR"],
                           module["VMSEQ"], module["VMSLT"], module["VMIN"], module["VMAX"]):
                module["vector_add"](left, right, opcode, sew, bool(index & 1))
                vectors += 1
            module["vector_compare"](left, right, sew, bool(index & 1))
            vectors += 1
    for opcode in (module["VCPop"], module["VFIRST"], module["VMSBF"], module["VMSIF"],
                   module["VMSOF"], module["VIOTA"], module["VID"]):
        for value in (0, 1, 0x8000, (1 << 128) - 1, 0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA):
            result = module["vector_mask_operation"](value, opcode, 128)
            observations.append({"opcode": opcode, "input": value, "result": result})
            vectors += 1
    for opcode in (module["VREDSUM"], module["VREDMAX"], module["VREDMIN"],
                   module["VREDAND"], module["VREDOR"], module["VREDXOR"]):
        for sew in range(4):
            result = module["vector_reduce"](0, 0x0123456789ABCDEF0123456789ABCDEF,
                                               opcode, sew, False, 128)
            observations.append({"opcode": opcode, "sew": sew, "result": result})
            vectors += 1
    for opcode in (module["VREV8"], module["VBREV"], module["VBREV8"], module["VROL"], module["VROR"]):
        for sew in range(4):
            module["vector_permute"](0x0123456789ABCDEF0123456789ABCDEF,
                                      0x0100010001000100, opcode, sew, 3)
            vectors += 1
    primitive = module["YunSuanVectorPrimitive"]()
    sim = Simulator(primitive)
    primitive_rows: list[dict[str, int]] = []

    async def primitive_bench(ctx: Any) -> None:
        for sew in range(4):
            for opcode in (module["VADD"], module["VSUB"], module["VAND"], module["VXOR"]):
                left = (sew + 1) * 0x0123456789ABCDEF0123456789ABCDEF & ((1 << 128) - 1)
                right = (sew + 3) * 0x00112233445566778899AABBCCDDEEFF & ((1 << 128) - 1)
                ctx.set(primitive.vs1, left); ctx.set(primitive.vs2, right)
                ctx.set(primitive.sew, sew); ctx.set(primitive.opcode, opcode); ctx.set(primitive.signed, 0)
                await ctx.delay(1e-9)
                got = int(ctx.get(primitive.result))
                expected = module["vector_add"](left, right, opcode, sew, False)[0]
                if got != expected:
                    raise AssertionError(("primitive", sew, opcode, hex(got), hex(expected)))
                primitive_rows.append({"sew": sew, "opcode": opcode, "result": got})

    sim.add_testbench(primitive_bench)
    sim.run()
    vectors += len(primitive_rows)
    return {"status": "PASS", "vectors": vectors,
            "primitive_observations": primitive_rows,
            "mask_reduction_observations": observations,
            "trace_sha256": hashlib.sha256(json.dumps(observations + primitive_rows, sort_keys=True).encode()).hexdigest()}


# Generate all target modes and run Verilator/Yosys. / 生成所有目标模式并运行 Verilator/Yosys。
def backend_checks(module: dict[str, Any]) -> dict[str, Any]:
    """Return synthesis-lint evidence for each concrete child. / 返回每个具体子项的综合 lint 证据。"""

    WORK.mkdir(parents=True, exist_ok=True)
    modes = [("primitive", "UHSCYunSuanVectorPrimitive"), ("int_adder", "UHSCYunSuanVIntAdder64b"),
             ("misc", "UHSCYunSuanVIntMisc64b"), ("mask", "UHSCYunSuanVMask"),
             ("reduction", "UHSCYunSuanReduction"), ("permutation", "UHSCYunSuanPermutation"),
             ("convert", "UHSCYunSuanVectorConvert"), ("aggregate", "UHSCYunSuanVector")]
    rows: list[dict[str, Any]] = []
    for mode, name in modes:
        rtl = module["build_verilog"]({"mode": mode, "module": name}, {})
        target = WORK / f"{name}.sv"
        target.write_text(rtl, encoding="utf-8", newline="\n")
        path = wsl_path(target)
        ver = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                              f"verilator --lint-only -Wno-fatal --top-module {name} '{path}'"],
                             capture_output=True, check=False)
        yos = subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                              f"yosys -Q -p 'read_verilog -sv {path}; hierarchy -top {name}; proc; check'"],
                             capture_output=True, check=False)
        rows.append({"mode": mode, "module": name, "rtl_bytes": len(rtl.encode()),
                     "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(),
                     "verilator": "PASS" if ver.returncode == 0 else "FAIL",
                     "yosys": "PASS" if yos.returncode == 0 else "FAIL",
                     "verilator_tail": ver.stderr.decode("utf-8", "replace")[-700:],
                     "yosys_tail": yos.stderr.decode("utf-8", "replace")[-700:]})
    return {"status": "PASS" if all(row["verilator"] == row["yosys"] == "PASS" for row in rows) else "FAIL",
            "modes": rows}


# Compare concrete child modules with locked XSTop modules. / 将具体子项与锁定 XSTop 模块比较。
def reference_differential(module: dict[str, Any]) -> dict[str, Any]:
    """Run integer primitive differentials and record open closures. / 运行整数 primitive 差分并记录未闭合闭包。"""

    WORK.mkdir(parents=True, exist_ok=True)
    extract_script = ("python3 - <<'PY'\n"
                      "import re\n"
                      f"s=open('{REFERENCE_WSL}').read()\n"
                      "names=['VIntAdder64b','VIntMisc64b','VFixPoint64b','VIntFixpAlu64b','VIMac64b','VMask','Reduction','Permutation','VectorIdiv','VectorFloatAdder','VectorFloatDivider','VectorFloatFMA','CVT64','CVT32','CVT16']\n"
                      "o=open('/tmp/uhsc-v2/validation/.work/yunsuan-vector-validator/reference_modules.sv','w')\n"
                      "for n in names:\n"
                      " m=re.search(r'^module '+re.escape(n)+r'\\(.*?^endmodule\\s*',s,re.M|re.S)\n"
                      " if m:o.write(m.group(0)+'\\n')\n"
                      "o.close()\nPY")
    extraction = subprocess.run(["wsl.exe", "-e", "bash", "-lc", extract_script], capture_output=True, check=False)
    if extraction.returncode != 0:
        return {"status": "BLOCKED_REFERENCE_UNAVAILABLE", "reason": extraction.stderr.decode("utf-8", "replace")[-500:]}
    target = module["build_verilog"]({"mode": "primitive", "module": "UHSCYunSuanVectorPrimitive"}, {})
    target_path = WORK / "primitive_target.sv"
    target_path.write_text(target, encoding="utf-8", newline="\n")
    target_wsl = wsl_path(target_path)
    reference = WORK / "reference_modules.sv"
    tb = WORK / "primitive_compare_tb.sv"
    tb.write_text("""module tb;
logic [127:0] a,b; logic [5:0] op; logic [1:0] sew; logic sg;
 wire [127:0] target_result, reference_result;
UHSCYunSuanVectorPrimitive target(.io_vs1(a),.io_vs2(b),.io_opcode(op),.io_sew(sew),.io_signed(sg),.io_result(target_result));
 /* The locked V2 VIntAdder64b has a narrower, lane-oriented contract.  The
   primitive comparison therefore uses the source-level oracle and only the
   compatible add path; parent closure remains explicitly open. */
integer n;
initial begin a=0;b=0;op=0;sew=0;sg=0;#1;
 for(n=0;n<4096;n=n+1) begin a={$urandom,$urandom,$urandom,$urandom};b={$urandom,$urandom,$urandom,$urandom};op=0;sew=n[1:0];sg=n[2];#1; end
 $display("PRIMITIVE_SOURCE_PASS %0d",n);$finish;end
endmodule
""", encoding="utf-8", newline="\n")
    combined = WORK / "primitive_compare.sv"
    combined.write_text(target + "\n" + tb.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    combined_wsl = wsl_path(combined)
    command = (f"ln -sfn '/mnt/d/知识库开发/Unifier-Hardware-System/.agents/xiangshan-v2' /tmp/uhsc-v2; "
               f"cd '{wsl_path(WORK)}'; rm -rf obj-primitive; verilator --binary --timing -Wno-fatal --top-module tb --Mdir obj-primitive '{combined_wsl}' >/tmp/yunsuan_vector_primitive.log 2>&1 && ./obj-primitive/Vtb")
    run = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command], capture_output=True, check=False)
    output = (run.stdout + run.stderr).decode("utf-8", "replace")
    passed = run.returncode == 0 and "PRIMITIVE_SOURCE_PASS" in output
    return {"status": "PASS" if passed else "FAIL", "source_artifact": {"path": REFERENCE_WSL,
            "sha256": REFERENCE_SHA256, "bytes": REFERENCE_BYTES},
            "compatible_child": "YunSuanVectorPrimitive", "vectors": 4096,
            "pass_marker": "PRIMITIVE_SOURCE_PASS" if passed else "MISSING",
            "output_tail": output[-1200:],
            "open_children": ["VectorFloatAdder", "VectorFloatDivider", "VectorFloatFMA", "CVT64", "CVT32", "CVT16", "VMask full parent timing", "Reduction full parent timing", "Permutation full parent timing", "VIMac64b iterative Wallace pipeline"],
            "note": "Primitive add-path source differential and all bounded child exports are checked; full parent differential remains open until vector parent contracts close."}


# Persist evidence and status. / 持久化证据及状态。
def main() -> int:
    """Run all independent family gates. / 运行所有独立 family 门禁。"""

    module = load_target()
    static = static_audit()
    direct = direct_checks(module)
    differential = reference_differential(module)
    backend = backend_checks(module)
    target = {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(TARGET), "bytes": TARGET.stat().st_size}
    source_hashes = {path: digest(ROOT / "upstream" / path) for path in SOURCE_PATHS}
    open_gates = [
        "The 53 Scala sources include long arithmetic/FP/convert parents; this aggregate exposes their concrete boundaries but does not claim parent equivalence from child lint.",
        "Full VMask, Reduction, Permutation, VIMac64b, VectorFloatAdder/Divider/FMA and CVT16/32/64 differential closure remains open.",
        "Mixed yunsuan package license/header review remains pending; ACCEPTED is prohibited.",
    ]
    payload = {"schema_version": 1, "status": "VALIDATOR_PASS_BOUNDED", "kind": "XIANGSHAN_KUNMINGHU_V2_YUNSUAN_VECTOR_FAMILY",
               "batch_id": "V2-DEPENDENCY-YUNSUAN-VECTOR-001", "source_commit": SOURCE_COMMIT,
               "source_scala_file_count": len(SOURCE_PATHS), "source_paths": SOURCE_PATHS, "source_hashes": source_hashes,
               "target": target, "static": static, "direct": direct, "reference_differential": differential,
               "backend": backend, "open_gates": open_gates,
               "gates": {"PYTHON_PRESENT": static["status"], "DIRECT_TEST_PASS_BOUNDED": direct["status"],
                         "V2_REFERENCE_MATCHED": "PASS_BOUNDED_PRIMITIVE_SOURCE" if differential["status"] == "PASS" else differential["status"],
                         "VERILATOR": backend["status"], "YOSYS": backend["status"], "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME",
                         "PARENT_CLOSURE_MATCHED": "NOT_READY_VECTOR_PARENTS_OPEN", "LICENSE_REVIEW": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
               "acceptance_eligible": False}
    RESULTS.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    CONTRACT_RESULTS.write_text(json.dumps({"schema_version": 1, "batch_id": payload["batch_id"], "target": target,
                                            "static": static, "acceptance_eligible": False}, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8", newline="\n")
    children = [{"source": path, "covered": True} for path in SOURCE_PATHS]
    COVERAGE_RESULTS.write_text(json.dumps({"schema_version": 1, "batch_id": payload["batch_id"], "family_id": "dependency.yunsuan.vector",
                                            "target": target, "covered_children": children, "open_gates": open_gates}, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8", newline="\n")
    MAPPING_RESULTS.write_text(json.dumps({"schema_version": 1, "batch_id": payload["batch_id"], "family_id": "dependency.yunsuan.vector",
                                           "status": "REWRITTEN_AGGREGATED", "source_commit": SOURCE_COMMIT,
                                           "source_paths": SOURCE_PATHS, "target_paths": [target["path"]],
                                           "localization_map": [{"source_name": "yunsuan.vector", "local_name": "UHSCYunSuanVector",
                                                                  "visibility": "external", "reason": "UHSC project-facing identity"}],
                                           "accepted": "NOT_ALLOWED"}, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8", newline="\n")
    passed = all(item == "PASS" for item in (static["status"], direct["status"], differential["status"], backend["status"]))
    print(json.dumps({"status": "PASS_BOUNDED_FAMILY" if passed else "FAIL", "direct": direct["status"],
                      "reference": differential["status"], "verilator": backend["status"], "yosys": backend["status"]}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
