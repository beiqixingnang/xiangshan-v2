"""Bounded BranchModule child differential for Kunminghu V2 Backend.
昆明湖 V2 Backend BranchModule 有界子闭包差分验证。
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
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.BranchModule-Hardware.py"
LOCKED = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
WORK = ROOT / "validation/.work/v2-backend-branch-child"
EVIDENCE = ROOT / "validation/v2-backend-branch-child-differential-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


def digest(data: bytes) -> str:
    """Hash exact bytes. / 对原始字节求摘要。"""
    return hashlib.sha256(data).hexdigest()


def load_target():
    """Load the Branch Build module. / 加载 Branch Build 模块。"""
    spec = importlib.util.spec_from_file_location("v2_branch_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_wsl(command: list[str]) -> dict[str, object]:
    """Run a bounded WSL command. / 运行有界 WSL 命令。"""
    # Convert workspace paths to WSL paths before invoking Linux tools.  A
    # Windows drive path is interpreted as a relative filename by Verilator
    # inside WSL, which would make the differential fail before compilation.
    converted: list[str] = []
    for item in command:
        candidate = Path(item)
        if candidate.is_absolute() and candidate.exists():
            path_result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(candidate)],
                                         capture_output=True, check=False)
            if path_result.returncode == 0:
                converted.append(path_result.stdout.decode("utf-8", "replace").strip())
                continue
        converted.append(item)
    rendered = " ".join(shlex.quote(item) for item in converted)
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered], capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "output_tail": output[-1600:], "output_sha256": digest(output.encode())}


def wsl_path(path: Path) -> str:
    """Map a repository path through the stable ASCII alias. / 通过稳定 ASCII 别名映射仓库路径。"""
    return "/tmp/uhsc-v2/" + path.resolve().relative_to(ROOT.resolve()).as_posix()


def prepare_alias() -> None:
    """Create the stable WSL alias. / 创建稳定 WSL 别名。"""
    subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                    "ln -sfn /mnt/d/*/Unifier-Hardware-System/.agents/xiangshan-v2 /tmp/uhsc-v2"],
                   capture_output=True, check=False)


def extract_module(name: str) -> bytes:
    """Extract one complete module from locked XSTop. / 从锁定 XSTop 提取完整模块。"""
    start = f"module {name}(".encode()
    active = False
    depth = 0
    lines: list[bytes] = []
    with LOCKED.open("rb") as stream:
        for line in stream:
            if not active and line.lstrip().startswith(start):
                active, depth = True, 1
            if active:
                lines.append(line)
                if line.lstrip().startswith(b"module ") and not line.lstrip().startswith(start):
                    depth += 1
                if line.lstrip().startswith(b"endmodule"):
                    depth -= 1
                    if depth == 0:
                        return b"".join(lines)
    raise RuntimeError(f"missing locked module {name}")


def source_reference() -> tuple[bytes, dict[str, object]]:
    """Prepare renamed locked BranchModule/SubModule sources. / 准备重命名锁定参考源。"""
    branch = extract_module("BranchModule").replace(b"module BranchModule(", b"module BranchModuleReference(")
    branch = branch.replace(b"SubModule subModule", b"SubModuleReference subModule")
    sub = extract_module("SubModule").replace(b"module SubModule(", b"module SubModuleReference(")
    payload = sub + b"\n" + branch
    return payload, {"branch_bytes": len(branch), "submodule_bytes": len(sub),
                     "module_payload_sha256": digest(payload)}


def main() -> int:
    """Run direct and locked-reference BranchModule differential. / 运行 direct 与锁定参考差分。"""
    prepare_alias()
    module = load_target()
    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / "BranchModule-target.sv"
    target.write_text(module.build_verilog(None, {}), encoding="utf-8", newline="\n")
    reference, reference_meta = source_reference()
    ref = WORK / "BranchModule-reference.sv"
    ref.write_bytes(reference)
    rng = random.Random(0xB12A)
    vectors = [(rng.getrandbits(64), rng.getrandbits(64), rng.randrange(1 << 9), rng.randrange(2)) for _ in range(2048)]
    direct_checks = 0
    for src0, src1, func, pred in vectors:
        expected = module.branch_reference(src0, src1, func, 64)
        branch_type = (func >> 1) & 7
        signed0 = src0 - (1 << 64) if src0 & (1 << 63) else src0
        signed1 = src1 - (1 << 64) if src1 & (1 << 63) else src1
        oracle = {0: src0 == src1, 2: signed0 < signed1, 4: src0 < src1}.get(branch_type, False) ^ bool(func & 1)
        assert expected == oracle
        direct_checks += 1
    lines = ["module tb; reg [63:0] src0,src1; reg [8:0] func; reg pred; wire t_taken,t_misp,r_taken,r_misp;",
             "BranchModule t(.io_src_0(src0),.io_src_1(src1),.io_func(func),.io_pred_taken(pred),.io_taken(t_taken),.io_mispredict(t_misp));",
             "BranchModuleReference r(.io_src_0(src0),.io_src_1(src1),.io_func(func),.io_pred_taken(pred),.io_taken(r_taken),.io_mispredict(r_misp));",
             "initial begin"]
    for index, (src0, src1, func, pred) in enumerate(vectors):
        lines.append(f"src0=64'h{src0:016x}; src1=64'h{src1:016x}; func=9'h{func:03x}; pred={pred}; #1; if(t_taken!==r_taken || t_misp!==r_misp) begin $display(\"MISMATCH {index}\"); $fatal(1); end")
    lines.append(f'$display("BACKEND_BRANCH_CHILD_DIFF_PASS {len(vectors)}"); $finish; end endmodule')
    tb = WORK / "branch-child-tb.sv"
    tb.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    obj = WORK / "obj"
    compile_result = run_wsl(["verilator", "--binary", "--timing", "-Wno-fatal", "--top-module", "tb", "--Mdir", wsl_path(obj), wsl_path(target), wsl_path(ref), wsl_path(tb)])
    run = run_wsl([wsl_path(obj / "Vtb")]) if compile_result["returncode"] == 0 else {"status": "SKIP"}
    target_verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", wsl_path(target)])
    target_yosys = run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {wsl_path(target)}; hierarchy -top BranchModule; proc; check; stat"])
    passed = compile_result["returncode"] == 0 and run.get("returncode") == 0 and "BACKEND_BRANCH_CHILD_DIFF_PASS" in str(run.get("output_tail", ""))
    locked_ok = LOCKED.is_file() and LOCKED.stat().st_size == 228590583 and digest(LOCKED.read_bytes()) == LOCKED_SHA256
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_BRANCH_CHILD_DIFFERENTIAL", "source_commit": SOURCE_COMMIT,
               "target": {"path": str(TARGET.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(TARGET.read_bytes())},
               "locked_reference": {"canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv", "xstop_sha256": LOCKED_SHA256, "immutable": locked_ok, "extracted_reference": reference_meta},
               "direct": {"status": "PASS", "vectors": len(vectors), "checks": direct_checks},
               "differential": {"status": "PASS" if passed else "FAIL", "vectors": len(vectors), "compile": compile_result, "run": run},
               "tool_gates": {"verilator": target_verilator, "yosys": target_yosys},
               "gates": {"DIRECT_TEST_PASS_BOUNDED": "PASS", "V2_REFERENCE_MATCHED": "PASS_BOUNDED" if passed else "FAIL", "VERILATOR": target_verilator["status"], "YOSYS": target_yosys["status"], "PARENT_CLOSURE_MATCHED": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
               "status": "PASS_BOUNDED_BRANCH_CHILD" if passed and locked_ok else "FAIL", "acceptance_eligible": False,
               "unclosed": ["BranchUnit/Backend ExuBlock parent integration remains pending.", "Full Backend semantic closure and license/user review remain pending."]}
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "vectors": len(vectors), "ACCEPTED": "NOT_ALLOWED"}, sort_keys=True))
    return 0 if payload["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
