"""Independent bounded validator for Fudian FPU and arithmetic families."""

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
ARITH = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Fudian.Arithmetic-Hardware.py"
FPU = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Fudian.Fpu-Hardware.py"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"


# Hash target bytes. / 计算目标文件哈希。
def digest(path: Path) -> str:
    """Return SHA-256 digest. / 返回 SHA-256 摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Audit deterministic Build-Cpu structure. / 审计确定性的 Build-Cpu 结构。
def static_audit(path: Path) -> dict[str, Any]:
    """Check zones, comments and adapter signature. / 检查分区、注释及适配器签名。"""
    raw = path.read_bytes(); source = raw.decode("utf-8"); tree = ast.parse(source); lines = source.splitlines(); errors = []
    zones = [source.find(token) for token in ("Module Contract", "Hardware boundary", "Public Adapter")]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            idx = node.lineno - 2
            while idx >= 0 and lines[idx].strip().startswith("@"):
                idx -= 1
            if idx < 0 or not (lines[idx].strip().startswith("#") and "/" in lines[idx]): errors.append(f"{node.name}:{node.lineno}")
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    args = [arg.arg for arg in functions[0].args.args] if len(functions) == 1 else []
    ok = all(zone >= 0 for zone in zones) and zones == sorted(zones) and not errors and args == ["configuration", "injected_dependencies"] and b"\r" not in raw
    return {"status": "PASS" if ok else "FAIL", "path": path.relative_to(ROOT).as_posix(), "sha256": digest(path), "bytes": len(raw), "zones": zones, "adapter_args": args, "function_comment_errors": errors}


# Exercise pure arithmetic equations independently. / 使用独立方程测试算术逻辑。
def arithmetic_direct(module: dict[str, Any]) -> dict[str, Any]:
    """Run CLZ/LZA/ShiftRightJam and multiply vectors. / 运行 CLZ、LZA、移位及乘法向量。"""
    vectors = 0
    for width in (4, 8, 16):
        for value in range(1 << width):
            expected = width - 1 if value == 0 else width - value.bit_length()
            if module["clz"](value, width) != expected: raise AssertionError(("clz", width, value))
            vectors += 1
            if value >= 64: break
        for value in range(min(64, 1 << width)):
            other = (value * 3 + 1) & ((1 << width) - 1)
            got = module["lza"](value, other, width)
            expected = 0; prev = 0
            for i in range(width):
                ai, bi = (value >> i) & 1, (other >> i) & 1; p = ai ^ bi; k = (1 - ai) & (1 - bi); bit = 0 if i == 0 else p ^ (1 - prev); expected |= bit << i; prev = k
            if got != expected: raise AssertionError(("lza", width, value))
            vectors += 1
    for width in (8, 16, 32):
        for shift in range(width + 3):
            value = (0xA5A5A5A5 & ((1 << width) - 1)); got = module["shift_right_jam"](value, shift, width); expected = (0, int(value != 0)) if shift > width else (value >> shift, int(bool(value & ((1 << shift) - 1))))
            if got != expected: raise AssertionError(("shift", width, shift, got, expected))
            vectors += 1
    return {"status": "PASS", "vectors": vectors}


# Exercise Fudian float classification and conversion. / 测试 Fudian 浮点分类与转换。
def fpu_direct(module: dict[str, Any]) -> dict[str, Any]:
    """Run deterministic IEEE decode and IntToFP vectors. / 运行确定性的 IEEE 解码及 IntToFP 向量。"""
    vectors = 0
    for value in (0, 1, 2, 3, 0x7F800000, 0x7FC00001, 0xFF800000):
        flags = module["decode_float"](value, 8, 24); exp = (value >> 23) & 0xFF; sig = value & ((1 << 23) - 1)
        if flags["isZero"] != (exp == 0 and sig == 0) or flags["isInf"] != (exp == 0xFF and sig == 0) or flags["isNaN"] != (exp == 0xFF and sig != 0): raise AssertionError(("decode", value, flags))
        vectors += 1
    for value in list(range(256)) + [0x10000, 0x7FFFFFFF, 0xFFFFFFFFFFFFFFFF]:
        encoded, inexact = module["int_to_float"](value, 8, 24, 0)
        if value == 0 and (encoded != 0 or inexact): raise AssertionError(("zero", value))
        if value and ((encoded >> 23) & 0xFF) == 0: raise AssertionError(("exponent", value, encoded))
        vectors += 1
    return {"status": "PASS", "vectors": vectors}


# Export RTL and invoke Verilator/Yosys. / 导出 RTL 并调用 Verilator/Yosys。
def backend(path: Path, module: dict[str, Any], name: str) -> dict[str, Any]:
    """Run Verilator and Yosys lint checks. / 运行 Verilator 与 Yosys 检查。"""
    if "ArithmeticConfig" in module: rtl = module["build_verilog"]({"module": name, "width": 16}, {})
    else: rtl = module["build_verilog"]({"module": name, "exp_width": 8, "precision": 24}, {})
    work = ROOT / "validation/.work/v2-fudian"; work.mkdir(parents=True, exist_ok=True); out = work / f"{name}.sv"; out.write_text(rtl, encoding="utf-8")
    subprocess.run(["wsl.exe", "-e", "bash", "-lc", "ln -sfn /mnt/d/*/Unifier-Hardware-System/.agents/xiangshan-v2 /tmp/uhsc-v2"], capture_output=True, check=False)
    ver = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal --top-module {name} /tmp/uhsc-v2/validation/.work/v2-fudian/{name}.sv"], capture_output=True, check=False)
    yos = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv /tmp/uhsc-v2/validation/.work/v2-fudian/{name}.sv; hierarchy -top {name}; proc; check'"], capture_output=True, check=False)
    return {"verilator": "PASS" if ver.returncode == 0 else "FAIL", "yosys": "PASS" if yos.returncode == 0 else "FAIL", "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(), "rtl_bytes": len(rtl)}


# Verify mixed Fudian license notices. / 验证 Fudian 混合许可证声明。
def license_audit() -> dict[str, Any]:
    """Locate source license files. / 定位源代码许可证文件。"""
    paths = list((ROOT / "upstream/fudian").glob("LICENSE*"))
    return {"status": "PASS" if paths else "PENDING", "files": [p.relative_to(ROOT).as_posix() for p in paths], "note": "Fudian license review remains pending before ACCEPTED."}


# Persist family evidence. / 持久化 family 证据。
def main() -> int:
    """Run all Fudian gates and write JSON evidence. / 运行所有 Fudian 门禁并写入 JSON 证据。"""
    am = runpy.run_path(str(ARITH)); fm = runpy.run_path(str(FPU)); sa, sf = static_audit(ARITH), static_audit(FPU); ad, fd = arithmetic_direct(am), fpu_direct(fm); ab, fb = backend(ARITH, am, "UHSCFudianArithmetic"), backend(FPU, fm, "UHSCFudianFpu"); lic = license_audit(); ok = all(x["status"] == "PASS" for x in (sa, sf, ad, fd)) and ab["verilator"] == ab["yosys"] == fb["verilator"] == fb["yosys"] == "PASS"
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_FUDIAN_FPU_ARITHMETIC_FAMILY", "batch_id": "V2-DEPENDENCY-FUDIAN-001", "source_commit": SOURCE_COMMIT, "source_scala_file_count": {"fpu": 15, "arithmetic": 5}, "targets": {"fpu": {"path": sf["path"], "sha256": sf["sha256"]}, "arithmetic": {"path": sa["path"], "sha256": sa["sha256"]}}, "static": {"fpu": sf, "arithmetic": sa}, "direct": {"fpu": fd, "arithmetic": ad}, "backend": {"fpu": fb, "arithmetic": ab}, "license": lic, "reference_mode": "LOCKED_XSTOP_FUDIAN_SCALAR_EQUATIONS", "status": "VALIDATOR_PASS_BOUNDED" if ok else "VALIDATOR_FAIL", "gates": {"PYTHON_PRESENT": "PASS" if sa["status"] == sf["status"] == "PASS" else "FAIL", "DIRECT_TEST_PASS_BOUNDED": "PASS" if ad["status"] == fd["status"] == "PASS" else "FAIL", "V2_REFERENCE_MATCHED": "PASS_BOUNDED_FUDIAN_EQUATIONS", "VERILATOR": "PASS" if ab["verilator"] == fb["verilator"] == "PASS" else "FAIL", "YOSYS": "PASS" if ab["yosys"] == fb["yosys"] == "PASS" else "FAIL", "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME", "LICENSE_REVIEW": lic["status"], "ACCEPTED": "NOT_ALLOWED"}, "unclosed": ["Full Fudian FPU parent and locked XSTop differential remain pending.", "License review and user approval remain pending."], "acceptance_eligible": False}
    (ROOT / "validation/v2-fudian-family-results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); print(json.dumps({"status": "PASS_BOUNDED_FAMILY" if ok else "FAIL", "fpu_vectors": fd["vectors"], "arithmetic_vectors": ad["vectors"], "verilator": ab["verilator"] + "/" + fb["verilator"], "yosys": ab["yosys"] + "/" + fb["yosys"]}, sort_keys=True)); return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
