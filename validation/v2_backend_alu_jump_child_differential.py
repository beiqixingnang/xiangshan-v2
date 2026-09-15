"""Bounded locked-reference differential for V2 ALU and jump child families.
V2 ALU 与跳转子族的锁定参考有界差分验证。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
ALU_TARGET = BUILD / "Build-Cpu.Backend.Fu.AluDataModule-Hardware.py"
JUMP_TARGET = BUILD / "Build-Cpu.Backend.Fu.JumpDataModule-Hardware.py"
LOCKED = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
WORK = ROOT / "validation/.work/v2-backend-alu-jump-child"
EVIDENCE = ROOT / "validation/v2-backend-alu-jump-child-differential-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


def digest(data: bytes) -> str:
    """Hash bytes exactly. / 对字节原样求摘要。"""
    return hashlib.sha256(data).hexdigest()


def load(path: Path, name: str):
    """Load a Build module by exact path. / 按精确路径加载 Build。"""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_wsl(command: list[str]) -> dict[str, object]:
    """Run a bounded WSL command. / 运行有界 WSL 命令。"""
    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered], capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "output_tail": output[-1800:], "output_sha256": digest(output.encode())}


def wsl_path(path: Path) -> str:
    """Map a Windows path to WSL without relying on ephemeral /tmp state.

    每次通过 wslpath 精确转换 Windows 路径，避免不同 wsl.exe 调用之间
    `/tmp` symlink 不持久导致 Verilator/Yosys 看不到文件。
    """
    mapped = subprocess.run(
        ["wsl.exe", "-e", "wslpath", "-a", str(path.resolve())],
        capture_output=True, check=False,
    )
    if mapped.returncode != 0:
        raise RuntimeError("wslpath failed: " + mapped.stderr.decode("utf-8", "replace"))
    value = mapped.stdout.decode("utf-8", "replace").strip()
    if not value.startswith("/"):
        raise RuntimeError(f"unexpected WSL path: {value!r}")
    return value


def prepare_alias() -> None:
    """Create stable ASCII alias. / 创建稳定 ASCII 别名。"""
    # Do not use a wildcard here: the repository lives below a non-ASCII
    # directory and wildcard expansion is locale/filesystem dependent.  Ask
    # WSL to resolve the exact Windows path, then create one stable ASCII
    # symlink consumed by Verilator/Yosys command lines.
    mapped = subprocess.run(
        ["wsl.exe", "-e", "wslpath", "-a", str(ROOT)],
        capture_output=True, check=False,
    )
    if mapped.returncode != 0:
        raise RuntimeError("wslpath failed: " + mapped.stderr.decode("utf-8", "replace"))
    wsl_root = mapped.stdout.decode("utf-8", "replace").strip()
    if not wsl_root.startswith("/"):
        raise RuntimeError(f"unexpected WSL path: {wsl_root!r}")
    command = f"ln -sfn -- {shlex.quote(wsl_root)} /tmp/uhsc-v2"
    linked = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", command],
        capture_output=True, check=False,
    )
    if linked.returncode != 0:
        raise RuntimeError("cannot create WSL alias: " + linked.stderr.decode("utf-8", "replace"))


def extract(name: str) -> bytes:
    """Extract one complete module from immutable XSTop. / 提取锁定模块。"""
    marker = f"module {name}(".encode()
    active = False
    depth = 0
    lines: list[bytes] = []
    with LOCKED.open("rb") as stream:
        for line in stream:
            if not active and line.lstrip().startswith(marker):
                active, depth = True, 1
            if active:
                lines.append(line)
                if line.lstrip().startswith(b"module ") and not line.lstrip().startswith(marker):
                    depth += 1
                if line.lstrip().startswith(b"endmodule"):
                    depth -= 1
                    if depth == 0:
                        return b"".join(lines)
    raise RuntimeError(name)


def locked_alu() -> bytes:
    """Extract ALU and its eight generated helper modules. / 提取 ALU 及八个帮助模块。"""
    names = ["AddModule", "SubModule", "LeftShiftModule", "RightShiftModule", "LeftShiftWordModule", "RightShiftWordModule", "ShiftResultSelect", "MiscResultSelect", "ConditionalZeroModule", "WordResultSelect", "AluResSel", "AluDataModule"]
    payload = b"\n".join(extract(name) for name in names)
    return payload


def direct_checks(alu, jump) -> dict[str, object]:
    """Run independent Python ALU/jump checks. / 运行独立 Python 检查。"""
    rng = random.Random(0xA17)  # deterministic seed
    alu_vectors = [(rng.getrandbits(64), rng.getrandbits(64), rng.randrange(512)) for _ in range(2048)]
    jump_vectors = [(rng.getrandbits(64), rng.getrandbits(64), rng.getrandbits(33), rng.randrange(32), rng.randrange(8), rng.randrange(2)) for _ in range(2048)]
    for src0, src1, func in alu_vectors:
        assert 0 <= alu.alu_reference(src0, src1, func) < (1 << 64)
    for src, pc, imm, off, func, _pred in jump_vectors:
        result = jump.jump_reference(src, pc, imm, off, func)
        assert len(result) == 3 and result[2] == bool(func & 2)
    return {"status": "PASS", "alu_vectors": len(alu_vectors), "jump_vectors": len(jump_vectors), "checks": len(alu_vectors) + len(jump_vectors)}


def main() -> int:
    """Run ALU/jump direct and locked differential gates. / 运行 ALU/跳转差分门禁。"""
    prepare_alias()
    alu = load(ALU_TARGET, "v2_alu_target")
    jump = load(JUMP_TARGET, "v2_jump_target")
    WORK.mkdir(parents=True, exist_ok=True)
    alu_rtl = WORK / "AluDataModule-target.sv"; alu_rtl.write_text(alu.build_verilog(None, {}), encoding="utf-8", newline="\n")
    jump_rtl = WORK / "JumpDataModule-target.sv"; jump_rtl.write_text(jump.build_verilog(None, {}), encoding="utf-8", newline="\n")
    alu_ref = WORK / "AluDataModule-reference.sv"; alu_ref.write_bytes(locked_alu().replace(b"module AluDataModule(", b"module AluDataModuleReference("))
    jump_ref = WORK / "JumpDataModule-reference.sv"; jump_ref.write_bytes(extract("JumpDataModule").replace(b"module JumpDataModule(", b"module JumpDataModuleReference("))
    direct = direct_checks(alu, jump)
    rng = random.Random(0xA17D)
    alu_vectors = [(rng.getrandbits(64), rng.getrandbits(64), rng.randrange(512)) for _ in range(1024)]
    jump_vectors = [(rng.getrandbits(64), rng.getrandbits(64), rng.getrandbits(33), rng.randrange(32), rng.randrange(8)) for _ in range(1024)]
    lines = ["module tb; reg [63:0] a0,a1,js,jpc; reg [8:0] af,jf; reg [32:0] ji; reg [4:0] jo; wire [63:0] ta,ra,jtr,jrr,jtt,jrt; wire ja,jb;",
             "AluDataModule ta_i(.io_src_0(a0),.io_src_1(a1),.io_func(af),.io_result(ta)); AluDataModuleReference ra_i(.io_src_0(a0),.io_src_1(a1),.io_func(af),.io_result(ra));",
             "JumpDataModule jt_i(.io_src(js),.io_pc(jpc),.io_imm(ji),.io_nextPcOffset(jo),.io_func(jf),.io_result(jtr),.io_target(jtt),.io_isAuipc(ja)); JumpDataModuleReference jr_i(.io_src(js),.io_pc(jpc),.io_imm(ji),.io_nextPcOffset(jo),.io_func(jf),.io_result(jrr),.io_target(jrt),.io_isAuipc(jb));",
             "initial begin"]
    for index, (a0, a1, af) in enumerate(alu_vectors):
        lines.append(f"a0=64'h{a0:016x}; a1=64'h{a1:016x}; af=9'h{af:03x}; #1; if(ta!==ra) begin $display(\"ALU_MISMATCH {index}\"); $fatal(1); end")
    for index, (js, jpc, ji, jo, jf) in enumerate(jump_vectors):
        lines.append(f"js=64'h{js:016x}; jpc=64'h{jpc:016x}; ji=33'h{ji:09x}; jo=5'h{jo:02x}; jf=9'h{jf:03x}; #1; if(jtr!==jrr || jtt!==jrt || ja!==jb) begin $display(\"JUMP_MISMATCH {index}\"); $fatal(1); end")
    lines.append(f'$display("BACKEND_ALU_JUMP_CHILD_DIFF_PASS {len(alu_vectors)+len(jump_vectors)}"); $finish; end endmodule')
    tb = WORK / "alu-jump-child-tb.sv"; tb.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    obj = WORK / "obj"
    compile_result = run_wsl(["verilator", "--binary", "--timing", "-Wno-fatal", "-Wno-WIDTHEXPAND", "-Wno-WIDTHTRUNC", "--top-module", "tb", "--Mdir", wsl_path(obj), wsl_path(alu_rtl), wsl_path(alu_ref), wsl_path(jump_rtl), wsl_path(jump_ref), wsl_path(tb)])
    run = run_wsl([wsl_path(obj / "Vtb")]) if compile_result["returncode"] == 0 else {"status": "SKIP"}
    alu_verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", wsl_path(alu_rtl)])
    jump_verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", wsl_path(jump_rtl)])
    alu_yosys = run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {wsl_path(alu_rtl)}; hierarchy -top AluDataModule; proc; check; stat"])
    jump_yosys = run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {wsl_path(jump_rtl)}; hierarchy -top JumpDataModule; proc; check; stat"])
    passed = compile_result["returncode"] == 0 and run.get("returncode") == 0 and "BACKEND_ALU_JUMP_CHILD_DIFF_PASS" in str(run.get("output_tail", ""))
    locked_ok = LOCKED.is_file() and LOCKED.stat().st_size == 228590583 and digest(LOCKED.read_bytes()) == LOCKED_SHA256
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_ALU_JUMP_CHILD_DIFFERENTIAL", "source_commit": SOURCE_COMMIT,
               "targets": {"AluDataModule": str(ALU_TARGET.relative_to(ROOT)).replace("\\", "/"), "JumpDataModule": str(JUMP_TARGET.relative_to(ROOT)).replace("\\", "/")},
               "locked_reference": {"canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv", "xstop_sha256": LOCKED_SHA256, "immutable": locked_ok, "modules": ["AluDataModule", "JumpDataModule"]},
               "direct": direct, "differential": {"status": "PASS" if passed else "FAIL", "alu_vectors": len(alu_vectors), "jump_vectors": len(jump_vectors), "compile": compile_result, "run": run},
               "tool_gates": {"alu_verilator": alu_verilator, "jump_verilator": jump_verilator, "alu_yosys": alu_yosys, "jump_yosys": jump_yosys},
               "gates": {"DIRECT_TEST_PASS_BOUNDED": direct["status"], "V2_REFERENCE_MATCHED": "PASS_BOUNDED" if passed else "FAIL", "VERILATOR": "PASS" if alu_verilator["status"] == jump_verilator["status"] == "PASS" else "FAIL", "YOSYS": "PASS" if alu_yosys["status"] == jump_yosys["status"] == "PASS" else "FAIL", "PARENT_CLOSURE_MATCHED": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
               "status": "PASS_BOUNDED_ALU_JUMP_CHILD" if passed and locked_ok else "FAIL", "acceptance_eligible": False,
               "unclosed": ["ALU/JumpUnit integration into ExuBlock and full Backend remains pending.", "License review and user approval remain pending."]}
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "vectors": len(alu_vectors)+len(jump_vectors), "ACCEPTED": "NOT_ALLOWED"}, sort_keys=True))
    return 0 if payload["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
