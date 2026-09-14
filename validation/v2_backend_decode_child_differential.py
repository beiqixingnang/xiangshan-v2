"""Independent V2 Backend decode-child differential validator.
独立的 V2 Backend 解码子闭包差分验证器。

The existing RiscvInst Build is exercised against an equation-level SV oracle;
this batch is intentionally bounded to the Decode child and does not promote
the Backend parent closure.
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

from amaranth.sim import Simulator

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Decode.Isa.Bitfield.RiscvInst-Hardware.py"
WORK = ROOT / "validation/.work/v2-backend-decode-child"
EVIDENCE = ROOT / "validation/v2-backend-decode-child-differential-results.json"
LOCKED = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


def digest(data: bytes) -> str:
    """Hash exact bytes. / 对原始字节求摘要。"""
    return hashlib.sha256(data).hexdigest()


def load_target():
    """Load the Build file by exact path. / 按精确路径加载 Build 文件。"""
    spec = importlib.util.spec_from_file_location("v2_backend_riscvinst", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_wsl(command: list[str]) -> dict[str, object]:
    """Run one bounded WSL tool command. / 运行一次有界 WSL 工具命令。"""
    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered], capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "output_tail": output[-1800:], "output_sha256": digest(output.encode())}


def wsl_path(path: Path) -> str:
    """Map a repository path to WSL. / 将仓库路径映射到 WSL。"""
    absolute = path.resolve()
    return "/mnt/" + absolute.drive[0].lower() + absolute.as_posix().split(":", 1)[1]


def direct_checks(module) -> dict[str, object]:
    """Run scalar field/predicate checks independently. / 独立运行标量字段谓词检查。"""
    rng = random.Random(0xD3C0DE)
    vectors = [0, 0xFFFFFFFF] + [rng.getrandbits(32) for _ in range(512)]
    checks = 0
    for value in vectors:
        for name, (lsb, width) in module.FIELD_RANGES.items():
            assert module.inst_field(value, name) == ((value >> lsb) & ((1 << width) - 1))
            checks += 1
        opcode5 = (value >> 2) & 0x1F
        width = (value >> 12) & 7
        assert bool(module.isAMOCAS(value)) == (opcode5 == 11 and (((value >> 25) & 0x7F) & 0x7C) == 0x14)
        assert bool(module.isVecStore(value)) == (opcode5 == 9 and (width == 0 or ((width >> 2) & 1)))
        assert bool(module.isVecLoad(value)) == (opcode5 == 1 and (width == 0 or ((width >> 2) & 1)))
        assert bool(module.isVecArith(value)) == (opcode5 == 21)
        checks += 4
    return {"status": "PASS", "input_vectors": len(vectors), "scalar_checks": checks}


def reference_sv() -> str:
    """Render an independent RISC-V field equation oracle. / 渲染独立位域方程 oracle。"""
    outputs = ["opcode", "opcode5", "rd", "funct3", "rs1", "rs2", "funct7", "width", "rnum",
               "is_amo_cas", "is_vec_store", "is_vec_load", "is_vec_arith", "is_opivv", "is_opfvv",
               "is_opmvv", "is_opivi", "is_opivx", "is_opfvf", "is_opmvx"]
    lines = ["module RiscvInstReference(inst," + ",".join(outputs) + ");", "input [31:0] inst;"]
    widths = {"opcode": 7, "opcode5": 5, "rd": 5, "funct3": 3, "rs1": 5, "rs2": 5, "funct7": 7, "width": 3, "rnum": 4}
    for name in outputs:
        lines.append(f"output [{widths[name]-1}:0] {name};" if name in widths else f"output {name};")
    lines += ["assign opcode=inst[6:0]; assign opcode5=inst[6:2]; assign rd=inst[11:7];",
              "assign funct3=inst[14:12]; assign rs1=inst[19:15]; assign rs2=inst[24:20];",
              "assign funct7=inst[31:25]; assign width=inst[14:12]; assign rnum=inst[23:20];",
              "assign is_amo_cas=(opcode5==5'd11)&&((funct7&7'h7c)==7'h14);",
              "assign is_vec_store=(opcode5==5'd9)&&((width==3'd0)||width[2]);",
              "assign is_vec_load=(opcode5==5'd1)&&((width==3'd0)||width[2]);",
              "assign is_vec_arith=(opcode5==5'd21);",
              "assign is_opivv=(opcode==7'h57)&&(funct3==3'd0); assign is_opfvv=(opcode==7'h57)&&(funct3==3'd1);",
              "assign is_opmvv=(opcode==7'h57)&&(funct3==3'd2); assign is_opivi=(opcode==7'h57)&&(funct3==3'd3);",
              "assign is_opivx=(opcode==7'h57)&&(funct3==3'd4); assign is_opfvf=(opcode==7'h57)&&(funct3==3'd5);",
              "assign is_opmvx=(opcode==7'h57)&&(funct3==3'd6);", "endmodule"]
    return "\n".join(lines) + "\n"


def run_differential(module) -> dict[str, object]:
    """Compile target/oracle and compare 1024 deterministic vectors. / 编译并差分比较 1024 个向量。"""
    WORK.mkdir(parents=True, exist_ok=True)
    target_rtl = WORK / "RiscvInst-target.sv"
    target_rtl.write_text(module.build_verilog(None, {}), encoding="utf-8", newline="\n")
    ref_rtl = WORK / "RiscvInst-reference.sv"
    ref_rtl.write_text(reference_sv(), encoding="utf-8", newline="\n")
    rng = random.Random(0x51A7)
    vectors = [0, 0xFFFFFFFF] + [rng.getrandbits(32) for _ in range(1022)]
    lines = ["module tb; reg [31:0] inst;", "wire [6:0] t_opcode,r_opcode; wire [4:0] t_opcode5,r_opcode5,t_rd,r_rd,t_rs1,r_rs1,t_rs2,r_rs2; wire [2:0] t_funct3,r_funct3,t_width,r_width; wire [6:0] t_funct7,r_funct7; wire [3:0] t_rnum,r_rnum;", "wire [10:0] t_pred,r_pred;",
             "RiscvInst t(.inst(inst),.opcode(t_opcode),.opcode5(t_opcode5),.rd(t_rd),.funct3(t_funct3),.rs1(t_rs1),.rs2(t_rs2),.funct7(t_funct7),.width(t_width),.rnum(t_rnum),.is_amo_cas(t_pred[0]),.is_vec_store(t_pred[1]),.is_vec_load(t_pred[2]),.is_vec_arith(t_pred[3]),.is_opivv(t_pred[4]),.is_opfvv(t_pred[5]),.is_opmvv(t_pred[6]),.is_opivi(t_pred[7]),.is_opivx(t_pred[8]),.is_opfvf(t_pred[9]),.is_opmvx(t_pred[10]));",
             "RiscvInstReference r(.inst(inst),.opcode(r_opcode),.opcode5(r_opcode5),.rd(r_rd),.funct3(r_funct3),.rs1(r_rs1),.rs2(r_rs2),.funct7(r_funct7),.width(r_width),.rnum(r_rnum),.is_amo_cas(r_pred[0]),.is_vec_store(r_pred[1]),.is_vec_load(r_pred[2]),.is_vec_arith(r_pred[3]),.is_opivv(r_pred[4]),.is_opfvv(r_pred[5]),.is_opmvv(r_pred[6]),.is_opivi(r_pred[7]),.is_opivx(r_pred[8]),.is_opfvf(r_pred[9]),.is_opmvx(r_pred[10]));", "initial begin"]
    for index, value in enumerate(vectors):
        lines.append(f"inst=32'h{value:08x}; #1; if ({' || '.join(f't_{n}!==r_{n}' for n in ['opcode','opcode5','rd','funct3','rs1','rs2','funct7','width','rnum'])} || t_pred!==r_pred) begin $display(\"MISMATCH {index}\"); $fatal(1); end")
    lines += [f'$display("BACKEND_DECODE_CHILD_DIFF_PASS {len(vectors)}"); $finish; end endmodule']
    tb = WORK / "decode-child-tb.sv"
    tb.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    obj = WORK / "obj"
    build = run_wsl(["verilator", "--binary", "--timing", "-Wno-fatal", "-Wno-WIDTHEXPAND", "-Wno-WIDTHTRUNC", "--top-module", "tb", "--Mdir", wsl_path(obj), wsl_path(target_rtl), wsl_path(ref_rtl), wsl_path(tb)])
    run = run_wsl([wsl_path(obj / "Vtb")]) if build["returncode"] == 0 else {"status": "SKIP"}
    passed = build["returncode"] == 0 and run.get("returncode") == 0 and "BACKEND_DECODE_CHILD_DIFF_PASS" in str(run.get("output_tail", ""))
    verilator = run_wsl(["verilator", "--lint-only", "-Wno-fatal", wsl_path(target_rtl)])
    yosys = run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {wsl_path(target_rtl)}; hierarchy -top RiscvInst; proc; check; stat"])
    return {"status": "PASS" if passed else "FAIL", "vectors": len(vectors), "build": build, "run": run,
            "verilator": verilator, "yosys": yosys, "trace_sha256": digest((str(run).encode()))}


def main() -> int:
    """Run the bounded decode child transaction. / 运行有界解码子事务。"""
    module = load_target()
    direct = direct_checks(module)
    differential = run_differential(module)
    locked_ok = LOCKED.is_file() and digest(LOCKED.read_bytes()) == LOCKED_SHA256
    payload = {"schema_version": 1, "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_DECODE_CHILD_DIFFERENTIAL",
               "source_commit": SOURCE_COMMIT, "target": str(TARGET.relative_to(ROOT)).replace("\\", "/"),
               "locked_reference": {"path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv", "sha256": LOCKED_SHA256, "immutable": locked_ok},
               "direct": direct, "differential": differential,
               "gates": {"DIRECT_TEST_PASS_BOUNDED": direct["status"], "V2_REFERENCE_MATCHED": differential["status"],
                         "VERILATOR": differential["verilator"]["status"], "YOSYS": differential["yosys"]["status"],
                         "PARENT_CLOSURE_MATCHED": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
               "status": "PASS_BOUNDED_DECODE_CHILD" if direct["status"] == "PASS" and differential["status"] == "PASS" else "FAIL",
               "acceptance_eligible": False,
               "unclosed": ["Backend DecodeUnit/DecodeStage integration remains pending.", "Issue/Rename/CSR/EXU parent closure remains pending.", "License review and user approval remain pending."]}
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "vectors": differential["vectors"], "direct_checks": direct["scalar_checks"], "ACCEPTED": "NOT_ALLOWED"}, sort_keys=True))
    return 0 if payload["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
