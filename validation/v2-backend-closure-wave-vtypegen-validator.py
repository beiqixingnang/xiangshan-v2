"""Stateful VTypeGen differential against the pinned generated leaf."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Cpu-Core-Backend.Decode.ControlFamily-Hardware.py"
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
REFERENCE = ROOT / "validation/reference-sv/VTypeGen.sv"
REFERENCE_CHILD = ROOT / "validation/reference-sv/VsetModule.sv"
WORK = ROOT / "validation/.work/v2-backend-closure-wave-vtypegen"
EVIDENCE = ROOT / "validation/v2-backend-closure-wave-vtypegen.json"
LOCKED_XSTOP = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
LOCKED_XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_SHA256 = "a98add4e587bcd7c0affe6f0d27509b9c8e4a2cd7fba0693d8e68b7254310f5f"
REFERENCE_CHILD_SHA256 = "b509ebe18af260ff013739ae03a5395494d8a749175f89e233b0accf41a4fe95"
EXPECTED_CASES = 6 * 2 * 8 * 8 * 8 * 4 + 15 + 1 + 32


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


def wsl_path(path: Path) -> str:
    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path.resolve())], capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace"))
    return result.stdout.decode("utf-8", "replace").strip()


def run_wsl(command: list[str]) -> dict[str, object]:
    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered], capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {
        "command": command,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "returncode": result.returncode,
        "output_tail": output[-1800:],
        "output_sha256": digest(output.encode()),
    }


def make_testbench(ports: list[tuple[str, str, int]]) -> str:
    inputs = [port for port in ports if port[1] == "input"]
    outputs = [port for port in ports if port[1] == "output"]
    declarations: list[str] = []
    clear_inputs: list[str] = []
    dut_connections: list[str] = []
    ref_connections: list[str] = []
    for name, _direction, width in inputs:
        shape = f"[{width - 1}:0] " if width > 1 else ""
        declarations.append(f"  reg {shape}{name};")
        clear_inputs.append(f"      {name} = 0;")
        dut_connections.append(f".{name}({name})")
        ref_connections.append(f".{name}({name})")
    for name, _direction, width in outputs:
        shape = f"[{width - 1}:0] " if width > 1 else ""
        declarations.extend((f"  wire {shape}dut_{name};", f"  wire {shape}ref_{name};"))
        dut_connections.append(f".{name}(dut_{name})")
        ref_connections.append(f".{name}(ref_{name})")
    outputs_dut = "{" + ", ".join(f"dut_{name}" for name, _d, _w in outputs) + "}"
    outputs_ref = "{" + ", ".join(f"ref_{name}" for name, _d, _w in outputs) + "}"
    lane_clear = "\n".join(
        f"      io_insts_{lane}_valid = 0;\n      io_insts_{lane}_bits = 0;"
        for lane in range(6)
    )
    lane_select = "\n".join(
        f"      if (lane_value == {lane}) begin\n"
        f"        io_insts_{lane}_valid = 1;\n"
        f"        io_insts_{lane}_bits = inst_value;\n"
        "      end"
        for lane in range(6)
    )
    return f"""module vtypegen_diff_tb;
{chr(10).join(declarations)}
  integer lane_value, ivli_value, sew_value, lmul_value, reserved_value, flags_value;
  integer a_value, b_value, combo_value, checked;
  reg [31:0] inst_value;
  VTypeGen dut({', '.join(dut_connections)});
  VTypeGen_reference reference({', '.join(ref_connections)});

  task clear_vtype_inputs;
    begin
{chr(10).join(clear_inputs)}
{lane_clear}
    end
  endtask

  task tick_and_compare;
    begin
      clock = 0; #1;
      clock = 1; #1;
      if ({outputs_dut} !== {outputs_ref})
        $fatal(1, "VTypeGen mismatch case=%0d dut=%h ref=%h", checked, {outputs_dut}, {outputs_ref});
      checked = checked + 1;
      clock = 0; #1;
    end
  endtask

  initial begin
    checked = 0;
    clear_vtype_inputs();
    clock = 0;
    reset = 0; #1;
    reset = 1;
    #1;
    if ({outputs_dut} !== {outputs_ref}) $fatal(1, "VTypeGen reset mismatch dut=%h ref=%h", {outputs_dut}, {outputs_ref});
    reset = 0; #1;

    // All six decode lanes, both VSET encodings, all VSEW/LMUL values,
    // reserved payloads, and both agnostic flags.
    for (lane_value = 0; lane_value < 6; lane_value = lane_value + 1)
      for (ivli_value = 0; ivli_value < 2; ivli_value = ivli_value + 1)
        for (sew_value = 0; sew_value < 8; sew_value = sew_value + 1)
          for (lmul_value = 0; lmul_value < 8; lmul_value = lmul_value + 1)
            for (reserved_value = 0; reserved_value < 8; reserved_value = reserved_value + 1)
              for (flags_value = 0; flags_value < 4; flags_value = flags_value + 1) begin
                clear_vtype_inputs();
                io_canUpdateVType = 1;
                inst_value = 32'h00007057 | ((lmul_value | (sew_value << 3) | ((flags_value & 1) << 6) | (((flags_value >> 1) & 1) << 7)) << 20);
                if (ivli_value != 0) inst_value = inst_value | 32'hc0000000 | ((reserved_value & 3) << 28);
                else inst_value = inst_value | (reserved_value << 28);
{lane_select}
                tick_and_compare();
              end

    // Multiple vsets in one decode group must choose the lowest lane.
    for (a_value = 0; a_value < 5; a_value = a_value + 1)
      for (b_value = a_value + 1; b_value < 6; b_value = b_value + 1) begin
        clear_vtype_inputs();
        io_canUpdateVType = 1;
        inst_value = 32'h00007057 | (8'h81 << 20);
        lane_value = a_value;
{lane_select}
        inst_value = 32'h00007057 | (8'h52 << 20);
        lane_value = b_value;
{lane_select}
        tick_and_compare();
      end

    // Seed architectural state, then exercise all write/walk/update priority
    // combinations while the decode lane also carries a vset instruction.
    clear_vtype_inputs();
    io_commitVType_vtype_valid = 1;
    io_commitVType_vtype_bits_vma = 1;
    io_commitVType_vtype_bits_vta = 0;
    io_commitVType_vtype_bits_vsew = 2;
    io_commitVType_vtype_bits_vlmul = 2;
    tick_and_compare();
    for (combo_value = 0; combo_value < 32; combo_value = combo_value + 1) begin
      clear_vtype_inputs();
      io_commitVType_hasVsetvl = combo_value[0];
      io_commitVType_vtype_valid = combo_value[1];
      io_walkVType_valid = combo_value[2];
      io_walkToArchVType = combo_value[3];
      io_canUpdateVType = combo_value[4];
      io_vsetvlVType_illegal = 1;
      io_vsetvlVType_vma = 1;
      io_vsetvlVType_vta = 1;
      io_vsetvlVType_vsew = 1;
      io_vsetvlVType_vlmul = 3;
      io_commitVType_vtype_bits_illegal = 0;
      io_commitVType_vtype_bits_vma = 0;
      io_commitVType_vtype_bits_vta = 1;
      io_commitVType_vtype_bits_vsew = 3;
      io_commitVType_vtype_bits_vlmul = 1;
      io_walkVType_bits_illegal = 0;
      io_walkVType_bits_vma = 1;
      io_walkVType_bits_vta = 0;
      io_walkVType_bits_vsew = 0;
      io_walkVType_bits_vlmul = 0;
      lane_value = 5;
      inst_value = 32'h00007057 | (8'hC5 << 20);
{lane_select}
      tick_and_compare();
    end
    if (checked != {EXPECTED_CASES}) $fatal(1, "VTypeGen count mismatch checked=%0d", checked);
    $display("VTYPEGEN_LOCKED_DIFF_PASS cases=%0d", checked);
    $finish;
  end
endmodule
""".replace("EXPECTED_CASES", str(EXPECTED_CASES))


def main() -> int:
    module = load_target()
    failures: list[str] = []
    py_compile.compile(str(TARGET), doraise=True)
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))["modules"]["VTypeGen"]
    expected_ports = [
        (str(port["name"]), str(port["direction"]), abs(int(str(port["width"]).strip("[]").split(":")[0]) - int(str(port["width"]).strip("[]").split(":")[1])) + 1 if ":" in str(port["width"]) else 1)
        for port in hierarchy["ports"]
    ]
    if list(module.PORT_SPECS["VTypeGen"]) != expected_ports:
        failures.append("VTypeGen ordered port ABI mismatch")

    reference_hash = digest(REFERENCE.read_bytes())
    child_hash = digest(REFERENCE_CHILD.read_bytes())
    if reference_hash != REFERENCE_SHA256:
        failures.append("VTypeGen reference source digest mismatch")
    if child_hash != REFERENCE_CHILD_SHA256:
        failures.append("VsetModule reference source digest mismatch")
    xstop = run_wsl(["sha256sum", LOCKED_XSTOP])
    xstop_hash = str(xstop["output_tail"]).split()[0] if xstop["status"] == "PASS" else None
    if xstop_hash != LOCKED_XSTOP_SHA256:
        failures.append("locked XSTop digest mismatch")

    rtl_first = module.build_verilog({"module": "VTypeGen"}, {})
    rtl_second = module.build_verilog({"module": "VTypeGen"}, {})
    if rtl_first != rtl_second:
        failures.append("VTypeGen same-name export is nondeterministic")
    renamed = REFERENCE.read_text(encoding="utf-8").replace("module VTypeGen(", "module VTypeGen_reference(", 1)
    if renamed == REFERENCE.read_text(encoding="utf-8"):
        failures.append("VTypeGen reference module declaration not found")
    WORK.mkdir(parents=True, exist_ok=True)
    dut_path = WORK / "VTypeGen_DUT.sv"
    ref_path = WORK / "VTypeGen_reference.sv"
    child_path = WORK / "VsetModule.sv"
    tb_path = WORK / "vtypegen_diff_tb.sv"
    dut_path.write_text(rtl_first, encoding="utf-8", newline="\n")
    ref_path.write_text(renamed, encoding="utf-8", newline="\n")
    child_path.write_bytes(REFERENCE_CHILD.read_bytes())
    tb_path.write_text(make_testbench(expected_ports), encoding="utf-8", newline="\n")
    obj_path = WORK / ("obj-" + digest(rtl_first.encode())[:12])
    wsl_dut, wsl_ref, wsl_child, wsl_tb, wsl_obj = map(wsl_path, (dut_path, ref_path, child_path, tb_path, obj_path))
    compile_result = run_wsl([
        "verilator", "--binary", "--timing", "-Wno-fatal", "--top-module", "vtypegen_diff_tb",
        "--Mdir", wsl_obj, wsl_dut, wsl_ref, wsl_child, wsl_tb,
    ])
    if compile_result["status"] == "PASS":
        diff_result = run_wsl([f"{wsl_obj}/Vvtypegen_diff_tb"])
    else:
        diff_result = {"status": "NOT_RUN", "reason": "Verilator compile failed"}
    if diff_result.get("status") != "PASS":
        failures.append("VTypeGen locked reference differential failed")

    export_path = WORK / "VTypeGen.sv"
    export_path.write_text(rtl_first, encoding="utf-8", newline="\n")
    linux_export = wsl_path(export_path)
    lint = run_wsl(["verilator", "--lint-only", "-Wno-fatal", linux_export])
    yosys_script = f'read_verilog -sv "{linux_export}"; hierarchy -check -top VTypeGen; proc; stat; check'
    yosys = run_wsl(["yosys", "-Q", "-p", yosys_script])
    for name, result in (("Verilator lint", lint), ("Yosys", yosys)):
        if result["status"] != "PASS":
            failures.append(f"{name} failed")

    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_CLOSURE_WAVE_VTYPEGEN",
        "batch_id": "V2-BACKEND-CLOSURE-WAVE-002",
        "member": "VTypeGen",
        "build_path": str(TARGET.relative_to(ROOT)).replace("\\", "/"),
        "build_sha256": digest(TARGET.read_bytes()),
        "locked_reference": {
            "xstop_sha256": xstop_hash,
            "expected_xstop_sha256": LOCKED_XSTOP_SHA256,
            "module": "VTypeGen",
            "module_sha256": reference_hash,
            "helper_module": "VsetModule",
            "helper_module_sha256": child_hash,
        },
        "port_abi": {"locked": len(expected_ports), "candidate": len(module.PORT_SPECS["VTypeGen"]), "match": expected_ports == list(module.PORT_SPECS["VTypeGen"])},
        "export": {"deterministic": rtl_first == rtl_second, "bytes": len(rtl_first.encode()), "sha256": digest(rtl_first.encode())},
        "reference_differential": {"status": diff_result.get("status"), "case_dimensions": {"single_lane_vsets": EXPECTED_CASES - 48, "priority_combinations": 32, "lane_pairs": 15}, "cases": EXPECTED_CASES, "compile": compile_result, "run": diff_result},
        "tool_gates": {"py_compile": "PASS", "verilator_lint": lint, "yosys": yosys},
        "gates": {"DIRECT_TEST_PASS_BOUNDED": "PASS_BOUNDED", "V2_REFERENCE_MATCHED": "PASS_BOUNDED_STATEFUL_DIFFERENTIAL" if diff_result.get("status") == "PASS" else "STRICT_PENDING", "FORMAL": "PENDING_ROOT_SERIAL_RAIL", "PARENT_CLOSURE_MATCHED": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
        "status": "DIRECT_TEST_PASS_BOUNDED" if not failures else "FAIL",
        "strict_delta": 0,
        "acceptance_eligible": False,
        "failures": failures,
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "member": "VTypeGen", "differential": diff_result.get("status"), "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
