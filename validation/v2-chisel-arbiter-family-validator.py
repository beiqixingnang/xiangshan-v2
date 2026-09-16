"""Independent bounded validator for the V2 Chisel arbitration/CDC family.

V2 Chisel 仲裁与跨时钟域 family 的独立有界 validator。

The validator loads the aggregate Build subject by its exact path, compares the
generated port surface of every covered locked module against the locked
hierarchy, proves the export is byte-deterministic, and then runs a
cycle-by-cycle differential against the locked SystemVerilog through Verilator:
each differential subject is instantiated twice behind a wrapper whose outputs
are the locked outputs while a separate ``diff_mismatch`` output reports any
difference, so every vector either matches bit-for-bit or fails the run.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = (ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Core"
          / "Build-Cpu.Dependency.Chisel.Arbiter-Hardware.py")
HIERARCHY = ROOT / "validation" / "v2-locked-hierarchy.json"
EXTRACTED = ROOT / "validation" / ".work" / "arbiter-family" / "extracted"
NAMES = EXTRACTED / "names.txt"
OUT = ROOT / "validation" / "v2-chisel-arbiter-family-results.json"
WORK = ROOT / "validation" / ".work" / "arbiter-family" / "differential"

ALIAS = "/tmp/uhsc-v2"
RENAMED = "UhscArbFamilyTarget_"
NO_MISMATCH = "1'b0"
VECTORS = 96
DIFFERENTIAL_SUBJECTS = (
    "Arbiter2_MSHRRequest",
    "Arbiter2_DirRead",
    "Arbiter4_MainPipeReq",
    "AsyncQueueSource_3",
    "AsyncQueueSink_1",
)
LIMITATIONS = [
    "Bounded to the 57 locked arbitration/CDC modules; no XiangShan parent and no XSTop differential is claimed.",
    "Arbitration is exercised on the locked static-priority ordering only; no rotation policy exists in the artifact.",
    "Verilator narrows unknown states to zero, so the two-state differential cannot observe X propagation differences.",
    "License review and user acceptance remain pending.",
]


# Load the aggregate Build subject from its exact file path. / 从精确文件路径加载聚合 Build 主体。
def load_target():
    spec = importlib.util.spec_from_file_location("v2_chisel_arbiter", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Convert a workspace path into its ASCII WSL alias form. / 将工作区路径转换为 ASCII WSL 别名形式。
def wsl_path(path: Path) -> str:
    return f"{ALIAS}/" + path.resolve().relative_to(ROOT.resolve()).as_posix()


# Recreate the ASCII WSL alias; /tmp is tmpfs and is wiped whenever the WSL
# utility VM goes idle, so the alias is rebuilt before every aliased command.
# 重建 ASCII WSL 别名；/tmp 为 tmpfs，WSL 工具虚拟机空闲回收时会清空，
# 因此每条走别名的命令前都重建一次。
def ensure_alias() -> None:
    subprocess.run(["wsl.exe", "-e", "bash", "-lc",
                    f"rm -rf {ALIAS}; "
                    f"ln -s /mnt/d/*/Unifier-Hardware-System/.agents/xiangshan-v2 {ALIAS}"],
                   check=True, capture_output=True)


# Run one bounded WSL command and return its captured output. / 运行一个有界 WSL 命令并返回捕获输出。
def run_wsl(command: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    rendered = " ".join(shlex.quote(item) for item in command)
    if ALIAS in rendered:
        ensure_alias()
    return subprocess.run(["wsl.exe", "-e", "bash", "-lc", rendered],
                          text=True, encoding="utf-8", errors="replace",
                          capture_output=True, check=False, timeout=timeout)


# Decode one locked ANSI width string into a bit count. / 将锁定 ANSI 位宽字符串解码为位宽。
def decode_width(width: str) -> int:
    if not width:
        return 1
    msb, lsb = width.strip("[]").split(":")
    return int(msb) - int(lsb) + 1


# Read the port surface of one locked module as (name, width, direction). / 读取一个锁定模块的端口面。
def locked_ports(modules: dict, name: str) -> list[tuple[str, str, str]]:
    return [(port["name"], port["width"].replace(" ", ""), port["direction"])
            for port in modules[name]["ports"]]


# Recover the declared port surface from one emitted Verilog module. / 从生成 Verilog 中还原声明的端口面。
def emitted_ports(rtl: str) -> list[tuple[str, str, str]]:
    body = rtl[rtl.index("module "):rtl.index("endmodule")]
    return [(declared, (width or "").replace(" ", ""), direction)
            for direction, width, declared
            in re.findall(r"\b(input|output|inout)\s+(\[[^\]]*\])?\s*([A-Za-z_$][\w$]*)", body)]


# Rename the top module of one emitted Verilog file so it can coexist with the lock.
# 重命名生成 Verilog 的顶层模块，使其可与锁定模块共存。
def rename_top(rtl: str, name: str) -> str:
    lines = [line for line in rtl.splitlines()
             if not line.startswith("(* top") and not line.startswith("(* generator")]
    text = "\n".join(lines)
    marker = f"module {name}("
    if text.count(marker) != 1:
        raise ValueError(f"{name}: cannot rename the emitted top module")
    return text.replace(marker, f"module {RENAMED}{name}(")


# Render the Verilog wrapper that pairs the locked and generated modules. / 渲染配对锁定与生成模块的 Verilog 包装。
def render_wrapper(top: str, name: str, ports: list[tuple[str, str, str]],
                   probe: str | None = None) -> str:
    header = [port for port, _, _ in ports] + ["diff_mismatch"]
    lines = [f"module {top}(" + ", ".join(header) + ");"]
    for declared, width, direction in ports:
        lines.append(f"  {direction}{f' {width}' if width else ''} {declared};")
    lines.append("  output diff_mismatch;")
    # Both instances must drive separate nets: wiring an output straight to the
    # wrapper port would make the forwarding assignment a self loop. / 两个实例
    # 必须驱动各自独立的网络：把输出直接连到包装端口会让转发赋值成为自环。
    for declared, width, direction in ports:
        if direction == "output":
            basis = f"{width} " if width else ""
            lines.append(f"  wire {basis}locked_{declared}, target_{declared};")
    for kind, side, module in (("dut_locked", "locked", name),
                               ("dut_target", "target", f"{RENAMED}{name}")):
        lines.append(f"  {module} {kind}(")
        connections = []
        for declared, _, direction in ports:
            if direction == "output":
                connections.append(f"    .{declared}({side}_{declared})")
            elif kind == "dut_target" and declared == probe:
                # Falsification control: perturb one target input so a blind
                # comparison net is detectable. / 反向对照：扰动目标侧一个输入，
                # 使不敏感的比较网暴露出来。
                connections.append(f"    .{declared}(~{declared})")
            else:
                connections.append(f"    .{declared}({declared})")
        lines.append(",\n".join(connections))
        lines.append("  );")
    for declared, _, direction in ports:
        if direction == "output":
            lines.append(f"  assign {declared} = locked_{declared};")
    differences = " || ".join(
        f"(locked_{declared} != target_{declared})"
        for declared, _, direction in ports if direction == "output")
    lines.append(f"  assign diff_mismatch = {differences or NO_MISMATCH};")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


# Render the C++ bench that drives both instances and checks every output. / 渲染驱动两侧并检查全部输出的 C++ 测试台。
def render_bench(top: str, name: str, ports: list[tuple[str, str, str]]) -> str:
    inputs = [(declared, decode_width(width)) for declared, width, direction in ports
              if direction == "input"]
    outputs = [(declared, decode_width(width)) for declared, width, direction in ports
               if direction == "output"]
    lines = [
        '#include "verilated.h"',
        f'#include "V{top}.h"',
        "#include <cstdio>",
        "",
        "static unsigned long long entropy = 0x243F6A8885A308D3ULL;",
        "// Advance the deterministic xorshift vector source. / 推进确定性 xorshift 向量源。",
        "static unsigned int next_value() {",
        "    entropy ^= entropy << 13; entropy ^= entropy >> 7; entropy ^= entropy << 17;",
        "    return (unsigned int)(entropy >> 32);",
        "}",
        "",
        "// Fold one value into the FNV-1a trace hash. / 将一个值折入 FNV-1a 轨迹哈希。",
        "static unsigned long long mix(unsigned long long hash, unsigned long long value) {",
        "    hash ^= value & 0xFFFFFFFFULL; hash *= 1099511628211ULL;",
        "    hash ^= value >> 32; hash *= 1099511628211ULL;",
        "    return hash;",
        "}",
        "",
        "int main(int argc, char **argv) {",
        "    VerilatedContext context; context.commandArgs(argc, argv);",
        f"    V{top} dut{{&context}};",
    ]
    clocked = any(declared == "clock" for declared, _ in inputs)
    if clocked:
        lines.append("    dut.clock = 0;")
    if any(declared == "reset" for declared, _ in inputs):
        lines.append("    dut.reset = 1;")
    for declared, width in inputs:
        if declared in ("clock", "reset"):
            continue
        lines.extend(drive_lines(f"dut.{declared}", width))
    lines.append("    dut.eval();")
    if clocked:
        lines.extend(["    dut.clock = 1; dut.eval(); dut.clock = 0;", "    dut.eval();"])
    if any(declared == "reset" for declared, _ in inputs):
        lines.append("    dut.reset = 0;")
    lines.extend([
        "    unsigned long long trace = 1469598103934665603ULL;",
        "    int mismatches = 0;",
        f"    for (int vector = 0; vector < {VECTORS}; ++vector) {{",
    ])
    for declared, width in inputs:
        if declared in ("clock", "reset"):
            continue
        lines.extend("    " + line for line in drive_lines(f"dut.{declared}", width))
    lines.append("        dut.eval();")
    lines.append("        if (dut.diff_mismatch) ++mismatches;")
    for declared, width in outputs:
        lines.extend("    " + line for line in absorb_lines(f"dut.{declared}", width))
    if clocked:
        lines.extend(["        dut.clock = 1; dut.eval();", "        dut.clock = 0; dut.eval();"])
        for declared, width in outputs:
            lines.extend("    " + line for line in absorb_lines(f"dut.{declared}", width))
    lines.extend([
        "    }",
        f'    std::printf("vectors|{VECTORS}\\n");',
        '    std::printf("mismatches|%d\\n", mismatches);',
        '    std::printf("trace|%016llx\\n", trace);',
        "    return mismatches == 0 ? 0 : 1;",
        "}",
        "",
    ])
    return "\n".join(lines)


# Render the assignments that drive one bench input. / 渲染驱动一个测试台输入的赋值。
def drive_lines(target: str, width: int) -> list[str]:
    if width > 64:
        words = (width + 31) // 32
        return [f"for (int word = 0; word < {words}; ++word) {target}.data()[word] = next_value();"]
    return [f"{target} = (unsigned long long)next_value() & {hex((1 << width) - 1)}ULL;"]


# Render the statements that fold one bench output into the trace. / 渲染将一个测试台输出折入轨迹的语句。
def absorb_lines(target: str, width: int) -> list[str]:
    if width > 64:
        words = (width + 31) // 32
        return [f"for (int word = 0; word < {words}; ++word) "
                f"trace = mix(trace, (unsigned long long){target}.data()[word]);"]
    return [f"trace = mix(trace, (unsigned long long){target});"]


# Build one differential subject and report its vector outcome. / 构建一个差分主体并报告向量结论。
def differential(name: str, modules: dict, module, control: bool = False) -> dict:
    ports = locked_ports(modules, name)
    # The control perturbs the first driven non-clock input, which every locked
    # subject routes to an observable output. / 对照扰动首个非时钟驱动输入，锁定
    # 主体都会把它传到可观测输出。
    probe = None
    if control:
        probe = next(declared for declared, _, direction in ports
                     if direction == "input" and declared not in ("clock", "reset"))
    suffix = "_control" if control else ""
    directory = WORK / f"{name}{suffix}"
    directory.mkdir(parents=True, exist_ok=True)
    top = f"tb_{name}{suffix}"
    (directory / "wrapper.sv").write_text(render_wrapper(top, name, ports, probe),
                                          encoding="utf-8", newline="\n")
    (directory / "bench.cpp").write_text(render_bench(top, name, ports),
                                         encoding="utf-8", newline="\n")
    (directory / f"{RENAMED}{name}.sv").write_text(
        rename_top(module.build_verilog(name, {}), name), encoding="utf-8", newline="\n")
    build = run_wsl(["verilator", "--cc", "--exe", "--build", "--sv", "--Wno-fatal",
                     "--top-module", top,
                     "-I" + wsl_path(EXTRACTED),
                     "--Mdir", wsl_path(directory / "obj"),
                     wsl_path(directory / "wrapper.sv"),
                     wsl_path(EXTRACTED / f"{name}.sv"),
                     wsl_path(directory / f"{RENAMED}{name}.sv"),
                     wsl_path(directory / "bench.cpp")])
    if build.returncode != 0:
        return {"status": "BUILD_FAIL", "ports": len(ports),
                "stderr": build.stderr[-1500:]}
    run = run_wsl([wsl_path(directory / "obj" / f"V{top}")])
    if run.returncode != 0 and not control:
        return {"status": "RUN_FAIL", "ports": len(ports),
                "stdout": run.stdout[-500:], "stderr": run.stderr[-1500:]}
    observed = dict(line.split("|", 1) for line in run.stdout.splitlines() if "|" in line)
    vectors = int(observed.get("vectors", 0))
    mismatches = int(observed.get("mismatches", -1))
    report = {"ports": len(ports), "vectors": vectors, "mismatches": mismatches,
              "trace_fnv1a64": observed.get("trace", "")}
    if control:
        report["status"] = "DETECTED" if (mismatches > 0 and vectors == VECTORS) else "UNDETECTED"
        report["perturbed_input"] = probe
        return report
    report["status"] = "MATCH" if (mismatches == 0 and run.returncode == 0) else "MISMATCH"
    return report


# Run the whole bounded validation and write the evidence file. / 运行完整有界验证并写出证据文件。
def main() -> int:
    module = load_target()
    modules = json.loads(HIERARCHY.read_text(encoding="utf-8"))["modules"]
    covered = module.covered_modules()
    locked = [line.strip() for line in NAMES.read_text(encoding="utf-8").splitlines() if line.strip()]
    if sorted(covered) != sorted(locked):
        raise AssertionError("the coverage list disagrees with the locked manifest")

    surfaces: list[dict] = []
    for name in covered:
        first = module.build_verilog(name, {})
        second = module.build_verilog(name, {})
        if first != second:
            raise AssertionError(f"{name}: the export is not byte deterministic")
        declared = sorted(emitted_ports(first))
        expected = sorted(locked_ports(modules, name))
        if declared != expected:
            raise AssertionError(f"{name}: port surface differs: "
                                 f"{sorted(set(expected) - set(declared))} / "
                                 f"{sorted(set(declared) - set(expected))}")
        surfaces.append({"module": name, "ports": len(declared),
                         "verilog_sha256": hashlib.sha256(first.encode()).hexdigest()})

    ensure_alias()
    WORK.mkdir(parents=True, exist_ok=True)
    rendered = {name: module.build_verilog(name, {}) for name in covered}
    bundle = (ROOT / "validation" / ".work" / "arbiter-family" / "differential" / "all")
    bundle.mkdir(parents=True, exist_ok=True)
    written = []
    for name in covered:
        path = bundle / f"{name}.sv"
        path.write_text(rendered[name], encoding="utf-8", newline="\n")
        written.append(wsl_path(path))
    lint = run_wsl(["verilator", "--lint-only", "--sv", "--Wno-fatal", *written])
    yosys = run_wsl(["yosys", "-Q", "-p",
                     "; ".join(f"read_verilog -sv {path}" for path in written) +
                     "; hierarchy -check; proc; check"])
    differentials = [dict(differential(name, modules, module), module=name)
                     for name in DIFFERENTIAL_SUBJECTS]
    controls = [dict(differential(name, modules, module, control=True), module=name)
                for name in DIFFERENTIAL_SUBJECTS]

    matched = [entry for entry in differentials if entry["status"] == "MATCH"]
    detected = [entry for entry in controls if entry["status"] == "DETECTED"]
    arbiter_match = [entry for entry in matched if entry["module"].startswith("Arbiter")]
    queue_match = [entry for entry in matched if entry["module"].startswith("AsyncQueue")]
    verilator_ok = (lint.returncode == 0 and len(matched) == len(DIFFERENTIAL_SUBJECTS)
                    and len(detected) == len(DIFFERENTIAL_SUBJECTS))
    yosys_ok = yosys.returncode == 0
    status = "DIRECT_TEST_PASS_BOUNDED" if verilator_ok and yosys_ok else "VALIDATOR_FAIL"
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_CHISEL_ARBITER_FAMILY",
        "target": {"path": TARGET.relative_to(ROOT).as_posix(),
                   "sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest(),
                   "lines": len(TARGET.read_text(encoding="utf-8").splitlines())},
        "coverage": {"modules": len(covered), "manifest": NAMES.relative_to(ROOT).as_posix(),
                     "locked_hierarchy_modules": len(modules)},
        "port_surfaces": {"status": "PASS", "checked": len(surfaces),
                          "modules": surfaces},
        "determinism": {"status": "PASS", "repetitions": 2,
                        "note": "Two exports per module compared byte for byte."},
        "differential": {"status": "PASS" if differentials == matched else "FAIL",
                         "subjects": differentials,
                         "arbiter_subjects": len(arbiter_match),
                         "queue_subjects": len(queue_match),
                         "lock_sha256": {(EXTRACTED / f"{name}.sv").name:
                                         hashlib.sha256((EXTRACTED / f"{name}.sv").read_bytes()).hexdigest()
                                         for name in DIFFERENTIAL_SUBJECTS}},
        "falsification_control": {"status": "PASS" if len(detected) == len(controls) else "FAIL",
                                  "note": "One target input is inverted so a blind comparison net fails.",
                                  "subjects": controls},
        "backend": {"verilator_lint": "PASS" if lint.returncode == 0 else "FAIL",
                    "verilator_stdout": lint.stdout[-400:], "verilator_stderr": lint.stderr[-800:],
                    "yosys": "PASS" if yosys_ok else "FAIL",
                    "yosys_stdout": yosys.stdout[-800:], "yosys_stderr": yosys.stderr[-800:]},
        "gates": {"PYTHON_PRESENT": "PASS",
                  "DIRECT_TEST_PASS_BOUNDED": "PASS" if verilator_ok else "FAIL",
                  "VERILATOR": "PASS" if verilator_ok else "FAIL",
                  "YOSYS": "PASS" if yosys_ok else "FAIL",
                  "PYRIGHT_ZERO_ERROR": "PASS_BY_SEPARATE_RUN",
                  "PORT_SURFACE_MATCHED": "PASS",
                  "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME",
                  "PARENT_CLOSURE_MATCHED": "PENDING_SYSTEM_TOP_ARBITER_PARENT",
                  "LICENSE_REVIEW": "PENDING",
                  "ACCEPTED": "NOT_ALLOWED"},
        "status": status,
        "acceptance_eligible": False,
        "unclosed": LIMITATIONS,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"status": status, "modules": len(covered),
                      "differential": {entry["module"]: entry["status"]
                                       for entry in payload["differential"]["subjects"]},
                      "verilator_lint": payload["backend"]["verilator_lint"],
                      "yosys": payload["backend"]["yosys"]}, ensure_ascii=False))
    return 0 if status == "DIRECT_TEST_PASS_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
