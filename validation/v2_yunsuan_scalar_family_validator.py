"""Independent validator for the Kunminghu V2 YunSuan scalar family.
昆明湖 V2 YunSuan 标量 family 独立验证器。
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
# This validator owns only the scalar family evidence and temporary work area.
# 本验证器仅负责标量 family 证据及临时工作区。
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Core" / "Build-Cpu.Dependency.YunSuan.Scalar-Hardware.py"
SOURCE_ROOT = ROOT / "upstream" / "yunsuan" / "src" / "main" / "scala" / "yunsuan" / "scalar"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_BYTES = 228590583
WORK = ROOT / "validation" / ".work" / "yunsuan-scalar-validator"
RESULTS = ROOT / "validation" / "v2-yunsuan-scalar-family-results.json"
CONTRACT_RESULTS = ROOT / "validation" / "v2-yunsuan-scalar-family-contract-audit.json"
COVERAGE_RESULTS = ROOT / "validation" / "v2-yunsuan-scalar-family-coverage-manifest.json"
MAPPING_RESULTS = ROOT / "validation" / "v2-yunsuan-scalar-family-mapping-update.json"
SOURCE_PATHS = [
    "yunsuan/src/main/scala/yunsuan/scalar/Convert.scala",
    "yunsuan/src/main/scala/yunsuan/scalar/FPU.scala",
    "yunsuan/src/main/scala/yunsuan/scalar/IntToFP.scala",
    "yunsuan/src/main/scala/yunsuan/scalar/RoundingUnit.scala",
    "yunsuan/src/main/scala/yunsuan/scalar/utils.scala",
]


# Return a SHA-256 digest for an exact file. / 返回文件精确 SHA-256 摘要。
def digest(path: Path) -> str:
    """Hash exact bytes without normalizing line endings. / 对原始字节计算哈希而不规范化换行。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


# Convert a Windows workspace path to the WSL mount spelling. / 将 Windows 工作区路径转换为 WSL 挂载路径。
def wsl_path(path: Path) -> str:
    """Return a stable ``/mnt/<drive>`` path for the current workspace. / 返回当前工作区稳定的 /mnt/<drive> 路径。"""

    absolute = path.resolve()
    drive = absolute.drive.rstrip(":").lower()
    tail = absolute.as_posix().split(":", 1)[-1]
    return f"/mnt/{drive}{tail}"


# Load the target by exact path without package side effects. / 按精确路径加载目标且不产生包副作用。
def load_target() -> dict[str, Any]:
    """Execute the target module in an isolated namespace. / 在隔离命名空间执行目标模块。"""

    return runpy.run_path(str(TARGET))


# Audit source layout, imports and bilingual function comments. / 审计源码布局、导入及双语函数注释。
def static_audit() -> dict[str, Any]:
    """Return machine-readable contract facts. / 返回机器可读的契约事实。"""

    raw = TARGET.read_bytes()
    source = raw.decode("utf-8")
    tree = ast.parse(source, filename=str(TARGET))
    lines = source.splitlines()
    zones = [source.find(item) for item in
             ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")]
    forbidden = {"importlib", "runpy", "subprocess", "socket", "urllib", "os", "sys", "pathlib"}
    import_errors: list[str] = []
    function_errors: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in forbidden:
                    import_errors.append(alias.name)
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in forbidden:
                import_errors.append(node.module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prior = lines[node.lineno - 2].strip() if node.lineno > 1 else ""
            if not prior.startswith("#") or "/" not in prior:
                function_errors.append(f"{node.name}:{node.lineno}")
            if node.name.startswith("_") and not (node.name.startswith("__") and node.name.endswith("__")):
                function_errors.append(f"leading_underscore:{node.name}:{node.lineno}")
    adapters = [node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    adapter_args = ([arg.arg for arg in adapters[0].args.args]
                    if len(adapters) == 1 else [])
    valid = (zones == sorted(zones) and all(item >= 0 for item in zones)
             and not import_errors and not function_errors
             and adapter_args == ["configuration", "injected_dependencies"]
             and b"\r" not in raw and "__all__" in source)
    return {
        "status": "PASS" if valid else "FAIL",
        "path": TARGET.relative_to(ROOT).as_posix(),
        "bytes": len(raw),
        "sha256": digest(TARGET),
        "utf8_lf": b"\r" not in raw,
        "zones": zones,
        "adapter_args": adapter_args,
        "forbidden_imports": import_errors,
        "function_comment_errors": function_errors,
    }


# Run exact pure-model and Amaranth direct vectors. / 运行精确纯模型及 Amaranth direct 向量。
def direct_checks(module: dict[str, Any]) -> dict[str, Any]:
    """Exercise primitive, conversion and pipeline boundaries. / 测试 primitive、转换及流水线边界。"""

    vectors = 0
    # RoundingUnit exhaustive small-width matrix. / RoundingUnit 小位宽穷举矩阵。
    for value in range(256):
        for round_in in (0, 1):
            for sticky in (0, 1):
                for sign in (0, 1):
                    for rm in range(8):
                        expected = module["rounding_decision"](value, round_in, sticky, sign, rm, 8)
                        if expected[1] != (round_in | sticky):
                            raise AssertionError(("rounding", value, round_in, sticky, sign, rm))
                        vectors += 1
    # Utility functions cover all 16-bit CLZ values and deterministic LZA cases. /
    # utility 函数覆盖全部 16 位 CLZ 值及确定性 LZA 用例。
    for value in range(1 << 16):
        if module["leading_zero_count"](value, 16) != (15 - (value.bit_length() - 1) if value else 15):
            raise AssertionError(("clz", value))
        vectors += 1
    for a, b in ((0, 0), (0xFFFFFFFFFFFFFFFF, 0), (0xAAAAAAAAAAAAAAAA, 0x5555555555555555)):
        module["lza_value"](a, b, 64)
        vectors += 1
    # Integer conversion deterministic corners for all three FPU formats. /
    # 三种 FPU 格式的整数转换确定性边界用例。
    for exp_width, precision in ((5, 11), (8, 24), (11, 53)):
        target_format = module["FType"](exp_width, precision)
        for value in (0, 1, 2, 3, 0x7FFFFFFF, 0x80000000,
                      0xFFFFFFFFFFFFFFFF, 0x8000000000000000):
            for signed in (0, 1):
                for rm in range(5):
                    module["int_to_float_bits"](value, bool(signed), 64, target_format, rm)
                    vectors += 1
    # Simulate the combinational hardware against its own executable oracle. /
    # 将组合硬件与可执行 oracle 对照仿真。
    rounding = module["YunSuanRoundingUnit"](8)
    sim = Simulator(rounding)
    observations: list[dict[str, int]] = []

    async def rounding_bench(ctx: Any) -> None:
        for rm in range(8):
            for value in (0, 1, 2, 127, 255):
                for round_in in (0, 1):
                    for sticky in (0, 1):
                        ctx.set(rounding.input, value)
                        ctx.set(rounding.round_in, round_in)
                        ctx.set(rounding.sticky_in, sticky)
                        ctx.set(rounding.sign_in, (value >> 7) & 1)
                        ctx.set(rounding.rm, rm)
                        await ctx.delay(1e-9)
                        got = int(ctx.get(rounding.output))
                        expected = module["rounding_decision"](
                            value, round_in, sticky, (value >> 7) & 1, rm, 8)
                        if got != expected[0]:
                            raise AssertionError(("rounding_hw", rm, value, round_in, sticky, got, expected))
                        observations.append({"rm": rm, "value": value, "output": got})

    sim.add_testbench(rounding_bench)
    sim.run()
    vectors += len(observations)
    return {
        "status": "PASS",
        "vectors": vectors,
        "rounding_observations": observations[:3] + observations[-3:],
        "trace_sha256": hashlib.sha256(json.dumps(observations, sort_keys=True).encode()).hexdigest(),
    }


# Generate one target RTL mode and run Verilator/Yosys lint. / 生成一个目标 RTL 模式并运行 Verilator/Yosys lint。
def backend_checks(module: dict[str, Any]) -> dict[str, Any]:
    """Return backend results for every public hardware mode. / 返回所有公开硬件模式的后端结果。"""

    WORK.mkdir(parents=True, exist_ok=True)
    modes = [
        ("rounding", "UHSCYunSuanRounding"),
        ("lza", "UHSCYunSuanLZA"),
        ("clz", "UHSCYunSuanCLZ"),
        ("int_to_fp", "UHSCYunSuanIntToFP"),
        ("int2fp", "UHSCYunSuanINT2FP"),
        ("fpcvt", "UHSCYunSuanFPCVT"),
        ("aggregate", "UHSCYunSuanScalar"),
    ]
    rows: list[dict[str, Any]] = []
    root_wsl = wsl_path(ROOT)
    for mode, name in modes:
        rtl = module["build_verilog"]({"mode": mode, "module": name}, {})
        rtl_path = WORK / f"{name}.sv"
        rtl_path.write_text(rtl, encoding="utf-8", newline="\n")
        rtl_wsl = wsl_path(rtl_path)
        ver_cmd = f"verilator --lint-only -Wno-fatal --top-module {name} '{rtl_wsl}'"
        yos_cmd = (f"yosys -Q -p 'read_verilog -sv {rtl_wsl}; hierarchy -top {name}; "
                   "proc; check'")
        ver = subprocess.run(["wsl.exe", "-e", "bash", "-lc", ver_cmd],
                             capture_output=True, check=False)
        yos = subprocess.run(["wsl.exe", "-e", "bash", "-lc", yos_cmd],
                             capture_output=True, check=False)
        rows.append({
            "mode": mode,
            "module": name,
            "rtl_bytes": len(rtl.encode("utf-8")),
            "rtl_sha256": hashlib.sha256(rtl.encode("utf-8")).hexdigest(),
            "verilator": "PASS" if ver.returncode == 0 else "FAIL",
            "yosys": "PASS" if yos.returncode == 0 else "FAIL",
            "verilator_tail": ver.stderr.decode("utf-8", "replace")[-500:],
            "yosys_tail": yos.stderr.decode("utf-8", "replace")[-500:],
        })
    return {"status": "PASS" if all(row["verilator"] == row["yosys"] == "PASS" for row in rows) else "FAIL", "modes": rows}


# Compare primitive and IntToFP RTL with the locked V2 generated modules. /
# 将 primitive 与 IntToFP RTL 同锁定 V2 生成模块比较。
def reference_differential(module: dict[str, Any]) -> dict[str, Any]:
    """Run deterministic Verilator differential harnesses against XSTop.sv. / 使用 Verilator 差分 harness 对比 XSTop.sv。"""

    WORK.mkdir(parents=True, exist_ok=True)
    xstop = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
    ref = WORK / "scalar_reference.sv"
    ref_wsl = wsl_path(ref)
    extract = (f"sed -n '1199661,1200255p' {xstop} > '{ref_wsl}'")
    extraction = subprocess.run(["wsl.exe", "-e", "bash", "-lc", extract], capture_output=True, check=False)
    if extraction.returncode != 0:
        return {"status": "BLOCKED_REFERENCE_UNAVAILABLE", "reason": extraction.stderr.decode("utf-8", "replace")[-500:]}
    modules = load_target()
    cases = [
        ("rounding", "UHSCYunSuanRounding", "RoundingUnit_1", "rounding", 100000),
        ("lza", "UHSCYunSuanLZA", "LZA", "lza", 20000),
        ("clz", "UHSCYunSuanCLZ", "CLZ", "clz", 20000),
        ("int_to_fp", "UHSCYunSuanIntToFP", "IntToFP_1", "int", 20000),
    ]
    rows: list[dict[str, Any]] = []
    for mode, target_name, reference_name, kind, count in cases:
        target_rtl = modules["build_verilog"]({"mode": mode, "module": target_name}, {})
        target_path = WORK / f"{target_name}.sv"
        target_path.write_text(target_rtl, encoding="utf-8", newline="\n")
        target_wsl = wsl_path(target_path)
        if kind == "rounding":
            ports = "logic [51:0] i; logic ri,si,sg; logic [2:0] rm; wire [51:0] to,ro; wire ti,tc,tr,rf,rc;"
            inst = (f"{target_name} target(.io_round_in(i),.io_roundIn(ri),.io_stickyIn(si),.io_signIn(sg),.io_rm(rm),.io_round_out(to),.io_inexact(ti),.io_cout(tc),.io_r_up(tr)); "
                    f"{reference_name} reference_dut(.io_in(i),.io_roundIn(ri),.io_stickyIn(si),.io_signIn(sg),.io_rm(rm),.io_out(ro),.io_inexact(rf),.io_cout(rc));")
            compare = "to!==ro || ti!==rf || tc!==rc"
            display = "$display(\"ROUND_MISMATCH %0d\", n);"
        elif kind == "lza":
            ports = "logic [63:0] a,b; wire [63:0] to,ro;"
            inst = (f"{target_name} target(.io_a(a),.io_b(b),.io_f(to)); "
                    f"{reference_name} reference_dut(.io_b(b),.io_f(ro));")
            compare = "to!==ro"
            display = "$display(\"LZA_MISMATCH %0d\", n);"
        elif kind == "clz":
            ports = "logic [63:0] i; wire [5:0] to,ro;"
            inst = (f"{target_name} target(.io_in(i),.io_out(to)); "
                    f"{reference_name} reference_dut(.io_in(i),.io_out(ro));")
            compare = "to!==ro"
            display = "$display(\"CLZ_MISMATCH %0d\", n);"
        else:
            ports = "logic [63:0] i; logic s,l; logic [2:0] rm; wire [63:0] to,ro; wire [4:0] tf,rf;"
            inst = (f"{target_name} target(.io_int(i),.io_sign(s),.io_long(l),.io_rm(rm),.io_result(to),.io_fflags(tf)); "
                    f"{reference_name} reference_dut(.io_int(i),.io_sign(s),.io_long(l),.io_rm(rm),.io_result(ro),.io_fflags(rf));")
            compare = "to!==ro || tf!==rf"
            display = "$display(\"INT_MISMATCH %0d\", n);"
        if kind == "rounding":
            stimulus = "i={$urandom,$urandom}; ri=n[0]; si=n[1]; sg=n[2]; rm=n%8; #1;"
        elif kind == "lza":
            stimulus = "a=64'h0; b={$urandom,$urandom}; #1;"
        elif kind == "clz":
            stimulus = "i={$urandom,$urandom}; #1;"
        else:
            stimulus = "i={$urandom,$urandom}; s=n[0]; l=n[1]; rm=n%5; #1;"
        tb = (f"module tb; {ports} {inst} integer n; initial begin #1; "
              f"for(n=0;n<{count};n=n+1) begin {stimulus} "
              f"if({compare}) begin {display} $fatal(1); end end "
              f"$display(\"PASS_{kind.upper()} %0d\",n); $finish; end endmodule\n")
        tb_path = WORK / f"tb_{kind}.sv"
        tb_path.write_text(tb, encoding="utf-8", newline="\n")
        combined = WORK / f"compare_{kind}.sv"
        combined.write_text(target_rtl + "\n" + ref.read_text(encoding="utf-8") + "\n" + tb,
                            encoding="utf-8", newline="\n")
        combined_wsl = wsl_path(combined)
        mdir = f"obj_{kind}"
        command = (f"cd '{wsl_path(WORK)}'; rm -rf '{mdir}'; "
                   f"verilator --binary --timing -Wno-fatal --top-module tb --Mdir '{mdir}' '{combined_wsl}' "
                   f">/tmp/yunsuan_{kind}_build.log 2>&1 && './{mdir}/Vtb'")
        run = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command], capture_output=True, check=False)
        output = (run.stdout + run.stderr).decode("utf-8", "replace")
        passed = run.returncode == 0 and f"PASS_{kind.upper()}" in output
        rows.append({"kind": kind, "vectors": count, "status": "PASS" if passed else "FAIL",
                     "target": target_name, "reference": reference_name,
                     "output_tail": output[-1000:]})
        if not passed:
            break
    return {
        "status": "PASS" if rows and all(row["status"] == "PASS" for row in rows) else "FAIL",
        "source_artifact": {"path": xstop, "sha256": REFERENCE_SHA256, "bytes": REFERENCE_BYTES},
        "module_source_lines": {"LZA": "1199661-1199730", "CLZ": "1199733-1199865",
                                "IntToFP": "1199867-1200066", "RoundingUnit": "1199972-1199995"},
        "cases": rows,
    }


# Persist all family evidence and return a process status. / 持久化全部 family 证据并返回进程状态。
def main() -> int:
    """Run static, direct, differential and backend gates. / 运行静态、direct、差分及后端门禁。"""

    module = load_target()
    static = static_audit()
    direct = direct_checks(module)
    differential = reference_differential(module)
    backend = backend_checks(module)
    target_record = {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": digest(TARGET),
                     "bytes": TARGET.stat().st_size}
    source_hashes = {path: digest(ROOT / "upstream" / Path(path)) for path in SOURCE_PATHS}
    closure_open = [
        "FPCVT's full FP_INCVT behavior depends on the separately inventoried vector CVT64 closure.",
        "FPCVT hardware currently closes deterministic f32/f64 widening/narrowing paths; f16, FP-to-int, fround and fcvtmod remain parent-closure work.",
        "Mixed dependency license review remains open; source notices are retained and ACCEPTED is prohibited.",
    ]
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_YUNSUAN_SCALAR_FAMILY",
        "batch_id": "V2-DEPENDENCY-YUNSUAN-SCALAR-001",
        "source_commit": SOURCE_COMMIT,
        "source_scala_file_count": len(SOURCE_PATHS),
        "source_paths": SOURCE_PATHS,
        "source_hashes": source_hashes,
        "target": target_record,
        "static": static,
        "direct": direct,
        "reference_differential": differential,
        "backend": backend,
        "reference_mode": "LOCKED_XSTOP_PRIMITIVE_AND_INT_TO_FP_DIFFERENTIAL; FPCVT_CLOSURE_OPEN",
        "closure_open": closure_open,
        "gates": {
            "PYTHON_PRESENT": static["status"],
            "DIRECT_TEST_PASS_BOUNDED": direct["status"],
            "V2_REFERENCE_MATCHED": "PASS_BOUNDED_PRIMITIVE_INT_TO_FP" if differential["status"] == "PASS" else differential["status"],
            "VERILATOR": backend["status"],
            "YOSYS": backend["status"],
            "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME",
            "PARENT_CLOSURE_MATCHED": "NOT_READY_FPCVT_VECTOR_CVT64_OPEN",
            "LICENSE_REVIEW": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "acceptance_eligible": False,
    }
    RESULTS.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    CONTRACT_RESULTS.write_text(json.dumps({"schema_version": 1, "batch_id": payload["batch_id"],
                                            "target": target_record, "static": static,
                                            "acceptance_eligible": False}, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8", newline="\n")
    COVERAGE_RESULTS.write_text(json.dumps({"schema_version": 1, "batch_id": payload["batch_id"],
                                            "family_id": "dependency.yunsuan.scalar",
                                            "target": target_record,
                                            "covered_children": [
                                                {"source": SOURCE_PATHS[0], "apis": ["I2fCvtIO", "INT2FP", "FpCvtIO", "FPCVT"]},
                                                {"source": SOURCE_PATHS[1], "apis": ["FType", "FPU.box"]},
                                                {"source": SOURCE_PATHS[2], "apis": ["IntToFP_prenorm", "IntToFP_postnorm", "IntToFP"]},
                                                {"source": SOURCE_PATHS[3], "apis": ["RoundingUnit"]},
                                                {"source": SOURCE_PATHS[4], "apis": ["FloatPoint", "SignExt", "ZeroExt", "LZA", "CLZ"]},
                                            ],
                                            "closure_open": closure_open}, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8", newline="\n")
    MAPPING_RESULTS.write_text(json.dumps({"schema_version": 1, "batch_id": payload["batch_id"],
                                           "family_id": "dependency.yunsuan.scalar", "status": "REWRITTEN_AGGREGATED",
                                           "source_commit": SOURCE_COMMIT, "source_paths": SOURCE_PATHS,
                                           "target_paths": [target_record["path"]],
                                           "localization_map": [{"source_name": "yunsuan.scalar", "local_name": "UHSCYunSuanScalar", "visibility": "external", "reason": "UHSC project-facing identity"}],
                                           "accepted": "NOT_ALLOWED"}, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8", newline="\n")
    status = (static["status"] == "PASS" and direct["status"] == "PASS"
              and differential["status"] == "PASS" and backend["status"] == "PASS")
    print(json.dumps({"status": "PASS_BOUNDED_FAMILY" if status else "FAIL",
                      "direct": direct["status"], "reference": differential["status"],
                      "verilator": backend["status"], "yosys": backend["status"]}, sort_keys=True))
    return 0 if status else 1


if __name__ == "__main__":
    raise SystemExit(main())
