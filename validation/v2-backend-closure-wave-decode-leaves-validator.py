"""Reference-check the V2 FP and integer-vector decode leaf implementations."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import random
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Backend.Decode.ControlFamily-Hardware.py"
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
SCALA_FP = ROOT / "upstream/src/main/scala/xiangshan/backend/decode/FPDecoder.scala"
ROCKET_INSTRUCTIONS = ROOT / "upstream/rocket-chip/src/main/scala/rocket/Instructions.scala"
SCALA_VI = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/wrapper/VIPU.scala"
YUNSUAN_TYPES = ROOT / "upstream/yunsuan/src/main/scala/yunsuan/package.scala"
YUNSUAN_OPCODES = ROOT / "upstream/yunsuan/src/main/scala/yunsuan/vector/VectorALU/VAluDecode.scala"
REFERENCES = {
    "FPDecoder": ROOT / "validation/reference-sv/FPDecoder.sv",
    "VIAluDecoder": ROOT / "validation/reference-sv/VIAluDecoder.sv",
}
WORK = ROOT / "validation/.work/v2-backend-closure-wave-decode-leaves"
EVIDENCE = ROOT / "validation/v2-backend-closure-wave-decode-leaves.json"
LOCKED_XSTOP = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
LOCKED_XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


def load_target() -> Any:
    spec = importlib.util.spec_from_file_location("v2_decode_leaf_target", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(TARGET)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_width(width: object) -> int:
    token = str(width)
    match = re.fullmatch(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def run_wsl(command: list[str]) -> dict[str, object]:
    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered], capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {
        "command": command,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "output_tail": output[-1600:],
        "output_sha256": digest(output.encode()),
    }


def wsl_path(path: Path) -> str:
    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path.resolve())], capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace"))
    return result.stdout.decode("utf-8", "replace").strip()


def parse_fp_cases() -> list[int]:
    """Build deterministic legal-pattern probes from the reviewed decoder table."""

    scala = SCALA_FP.read_text(encoding="utf-8")
    rocket = ROCKET_INSTRUCTIONS.read_text(encoding="utf-8")
    patterns = {
        name: pattern
        for name, pattern in re.findall(
            r'^\s*def\s+([A-Z][A-Z0-9_]*)\s*=\s*BitPat\("b([01?]{32})"\)',
            rocket,
            re.MULTILINE,
        )
    }
    names: set[str] = set()
    for group in ("single", "double", "half"):
        declaration = re.search(rf"val\s+{group}\s*:\s*Array[^\n]*=\s*Array\(", scala)
        if declaration is None:
            raise ValueError(f"cannot locate FP instruction table {group}")
        start = declaration.start()
        end = scala.index("\n  )", start)
        names.update(re.findall(r"^\s*([A-Z][A-Z0-9_]*)\s*->\s*List\(", scala[start:end], re.MULTILINE))
    for group in ("isFP16Instrs", "isFP32Instrs", "isFP64Instrs", "isSew2Cvts", "isSew2Cvth"):
        match = re.search(rf"val\s+{group}\s*=\s*Seq\((.*?)\n\s*\)", scala, re.DOTALL)
        if match is not None:
            body = re.sub(r"//[^\n]*", "", match.group(1))
            names.update(re.findall(r"\b[A-Z][A-Z0-9_]*\b", body))
    missing = sorted(name for name in names if name not in patterns)
    if missing:
        raise ValueError("FP instruction constants missing from the pinned ISA table: " + ", ".join(missing))

    generator = random.Random(0xFDEC0DE)
    cases: set[int] = set()
    for name in sorted(names):
        pattern = patterns[name]
        mask = int("".join("0" if bit == "?" else "1" for bit in pattern), 2)
        value = int("".join("0" if bit in "?0" else "1" for bit in pattern), 2)
        free = (~mask) & 0xFFFFFFFF
        cases.add(value)
        cases.add(value | free)
        for _ in range(4):
            cases.add(value | (generator.getrandbits(32) & free))
    return sorted(cases)


def make_comb_testbench(ports: list[tuple[str, str, int]], cases: list[int], input_name: str, top: str) -> str:
    inputs = [port for port in ports if port[1] == "input"]
    outputs = [port for port in ports if port[1] == "output"]
    declarations: list[str] = []
    dut_connections: list[str] = []
    ref_connections: list[str] = []
    for name, _direction, width in inputs:
        shape = f"[{width - 1}:0] " if width > 1 else ""
        declarations.append(f"  reg {shape}{name};")
        dut_connections.append(f".{name}({name})")
        ref_connections.append(f".{name}({name})")
    for name, _direction, width in outputs:
        shape = f"[{width - 1}:0] " if width > 1 else ""
        declarations.extend((f"  wire {shape}dut_{name};", f"  wire {shape}ref_{name};"))
        dut_connections.append(f".{name}(dut_{name})")
        ref_connections.append(f".{name}(ref_{name})")
    dut_outputs = "{" + ", ".join(f"dut_{name}" for name, _d, _w in outputs) + "}"
    ref_outputs = "{" + ", ".join(f"ref_{name}" for name, _d, _w in outputs) + "}"
    test_inputs = "\n".join(
        f"      {input_name} = 32'h{value:08x}; #1;\n"
        f"      if ({dut_outputs} !== {ref_outputs})\n"
        f"        $fatal(1, \"{top} mismatch vector=%0d input=%h dut=%h ref=%h\", index, {input_name}, {dut_outputs}, {ref_outputs});\n"
        "      index = index + 1;"
        for value in cases
    )
    return f"""module {top.lower()}_diff_tb;
{chr(10).join(declarations)}
  integer index;
  {top} dut({', '.join(dut_connections)});
  {top}_reference reference({', '.join(ref_connections)});
  initial begin
    index = 0;
{test_inputs}
    $display(\"{top.upper()}_LOCKED_DIFF_PASS cases=%0d\", index);
    $finish;
  end
endmodule
"""


def check_member(module: Any, member: str, ref_path: Path, table: dict[str, Any]) -> dict[str, object]:
    ports = list(module.PORT_SPECS[member])
    expected = [
        (str(port["name"]), str(port["direction"]), parse_width(port.get("width", "")))
        for port in table[member]["ports"]
    ]
    actual_abi = expected == ports
    rtl = module.build_verilog({"module": member}, {})
    deterministic = rtl == module.build_verilog({"module": member}, {})
    source_ref = ref_path.read_text(encoding="utf-8")
    declaration = f"module {member}("
    if source_ref.count(declaration) != 1:
        raise ValueError(f"expected one reference module declaration: {member}")
    ref_text = source_ref.replace(declaration, f"module {member}_reference(", 1)

    if member == "VIAluDecoder":
        cases = list(range(256))
        input_name = "io_in_fuOpType"
    else:
        cases = parse_fp_cases()
        input_name = "io_instr"
    WORK.mkdir(parents=True, exist_ok=True)
    dut_path = WORK / f"{member}_DUT.sv"
    ref_file = WORK / f"{member}_reference.sv"
    tb_path = WORK / f"{member.lower()}_diff_tb.sv"
    dut_path.write_text(rtl, encoding="utf-8", newline="\n")
    ref_file.write_text(ref_text, encoding="utf-8", newline="\n")
    tb_path.write_text(make_comb_testbench(ports, cases, input_name, member), encoding="utf-8", newline="\n")
    obj_dir = WORK / f"obj-{member.lower()}-{digest(rtl.encode())[:10]}"
    wsl_dut, wsl_ref, wsl_tb, wsl_obj = map(wsl_path, (dut_path, ref_file, tb_path, obj_dir))
    compile_diff = run_wsl([
        "verilator", "--binary", "--timing", "-Wno-fatal", "--top-module", f"{member.lower()}_diff_tb",
        "--Mdir", wsl_obj, wsl_dut, wsl_ref, wsl_tb,
    ])
    run_diff = run_wsl([f"{wsl_obj}/V{member.lower()}_diff_tb"]) if compile_diff["status"] == "PASS" else {"status": "NOT_RUN"}

    pyright_status = None
    output_path = WORK / f"{member}.sv"
    output_path.write_text(rtl, encoding="utf-8", newline="\n")
    linux_output = wsl_path(output_path)
    lint = run_wsl(["verilator", "--lint-only", "-Wno-fatal", linux_output])
    yosys = run_wsl(["yosys", "-Q", "-p", f'read_verilog -sv "{linux_output}"; hierarchy -check -top {member}; proc; stat; check'])
    return {
        "status": "PASS" if actual_abi and deterministic and compile_diff["status"] == "PASS" and run_diff.get("status") == "PASS" and lint["status"] == "PASS" and yosys["status"] == "PASS" else "FAIL",
        "abi": {"locked_ports": len(expected), "candidate_ports": len(ports), "match": actual_abi},
        "export": {"deterministic": deterministic, "bytes": len(rtl.encode()), "sha256": digest(rtl.encode())},
        "vectors": len(cases),
        "reference_sha256": digest(ref_path.read_bytes()),
        "reference_differential": {"compile": compile_diff, "run": run_diff},
        "verilator_lint": lint,
        "yosys": yosys,
    }


def main() -> int:
    module = load_target()
    py_compile.compile(str(TARGET), doraise=True)
    lock = run_wsl(["sha256sum", "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"])
    lock_hash = str(lock["output_tail"]).split()[0] if lock["status"] == "PASS" else None
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))["modules"]
    failures: list[str] = []
    results: dict[str, Any] = {}
    refs: dict[str, str] = {}
    if lock_hash != LOCKED_XSTOP_SHA256:
        failures.append("locked XSTop hash mismatch")
    for member, path in REFERENCES.items():
        result = check_member(module, member, path, hierarchy)
        results[member] = result
        refs[member] = digest(path.read_bytes())
        if result["status"] != "PASS":
            failures.append(f"locked differential or static gate failed: {member}")
    scala_sources = {
        str(path.relative_to(ROOT)).replace("\\", "/"): digest(path.read_bytes())
        for path in (SCALA_FP, SCALA_VI, YUNSUAN_TYPES, YUNSUAN_OPCODES)
    }
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_CLOSURE_WAVE_DECODE_LEAVES",
        "batch_id": "V2-BACKEND-CLOSURE-WAVE-003",
        "members": ["FPDecoder", "VIAluDecoder"],
        "build_path": str(TARGET.relative_to(ROOT)).replace("\\", "/"),
        "build_sha256": digest(TARGET.read_bytes()),
        "locked_xstop_sha256": lock_hash,
        "source_scala_sha256": scala_sources,
        "reference_sha256": refs,
        "member_results": results,
        "gates": {
            "DIRECT_TEST_PASS_BOUNDED": "PASS_BOUNDED" if not failures else "FAIL",
            "V2_REFERENCE_MATCHED": "PASS_BOUNDED_REFERENCE_DIFFERENTIAL" if not failures else "PENDING",
            "FORMAL": "PENDING_ROOT_SERIAL_RAIL",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "DIRECT_TEST_PASS_BOUNDED" if not failures else "FAIL",
        "strict_delta": 0,
        "acceptance_eligible": False,
        "failures": failures,
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "members": {name: value["status"] for name, value in results.items()}, "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
