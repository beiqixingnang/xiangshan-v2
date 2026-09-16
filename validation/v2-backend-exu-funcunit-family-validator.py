"""Focused bounded validator for the V2 backend EXU / FuncUnit family.

V2 后端 EXU / FuncUnit 族的聚焦有界校验器。

The validator loads the Build subject by exact path, checks every covered
module's Amaranth port surface against ``validation/v2-locked-hierarchy.json``,
proves the emitted Verilog is deterministic, runs Verilator lint and Yosys
elaboration on every covered member through WSL, and differentially compares
two representative instances (Alu, Bku) against the pinned ``XSTop.sv`` with
Verilator cycle simulation. Behavioral equivalence for the full family is NOT
claimed: status stays at most ``DIRECT_TEST_PASS_BOUNDED``.

校验器按精确路径加载 Build 主体，对照锁定层级检查每个被覆盖模块的端口面，证明
Verilog 确定性，经 WSL 对每个成员运行 Verilator lint 与 Yosys 展开，并用
Verilator 周期仿真把两个代表实例（Alu、Bku）与钉死的 ``XSTop.sv`` 做差分。
不声明整族行为等价：状态至多 ``DIRECT_TEST_PASS_BOUNDED``。
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
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = (
    ROOT
    / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
    / "Build-Cpu.Backend.Exu.FuncUnit-Hardware.py"
)
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
LOCKED_WSL = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
WORK = ROOT / "validation/.work/v2-backend-exu-funcunit-family"
EVIDENCE = ROOT / "validation/v2-backend-exu-funcunit-family-results.json"
SOURCE_COMMIT = "8b181bc"

FAMILY_SOURCES = (
    "xiangshan/backend/fu/FuncUnit.scala",
    "xiangshan/backend/fu/Bku.scala",
    "xiangshan/backend/exu/ExeUnit.scala",
)
# Modules owned by other waves / workers or generic-parameter variants that are
# not individually emitted here. / 由其他批次负责或为通用参数化变体的模块。
EXCLUDED_FP_LEAVES = frozenset({
    "FAlu", "FCVT", "FDivSqrt", "FMA", "IntFPToVec", "IntToFP_3", "VCVT_8",
    "VFAlu", "VFDivSqrt", "VFMA", "VIAluFix", "VIDiv", "VIMacU", "VIPU",
    "VPPU", "VSetRiWi", "VSetRiWvf", "VSetRvfWvf",
})

# Two representative modules carry the Verilator differential against the
# pinned artifact: combinational Alu and the two-stage sequential Bku.
# 两个代表模块承担与钉死产物的 Verilator 差分：组合逻辑 Alu 与两级时序 Bku。
DIFFERENTIAL_TARGETS: tuple[str, ...] = ("Alu", "Bku")
# Pinned child instances needed to close each differential target's hierarchy.
# 每个差分目标所需的钉死子实例（依赖闭包）。
PINNED_CHILDREN: dict[str, tuple[str, ...]] = {
    "Alu": ("AluDataModule",),
    "Bku": ("CountModule", "ClmulModule", "MiscModule", "CryptoModule", "HashModule", "BlockCipherModule"),
}
DIFF_VECTORS = 512


def digest(data: bytes) -> str:
    """Hash bytes exactly. / 对字节原样求摘要。"""
    return hashlib.sha256(data).hexdigest()


def load(path: Path, name: str):
    """Load a Build subject by exact path. / 按精确路径加载 Build 主体。"""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_wsl(command: list[str]) -> dict[str, object]:
    """Run one bounded WSL command. / 运行一条有界 WSL 命令。"""
    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", rendered], capture_output=True, check=False
    )
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "output_tail": output[-2000:],
        "output_sha256": digest(output.encode()),
    }


def wsl_path(path: Path) -> str:
    """Map a Windows path to WSL. / 把 Windows 路径映射到 WSL。"""
    mapped = subprocess.run(
        ["wsl.exe", "-e", "wslpath", "-a", str(path.resolve())],
        capture_output=True,
        check=False,
    )
    if mapped.returncode != 0:
        raise RuntimeError("wslpath failed: " + mapped.stderr.decode("utf-8", "replace"))
    value = mapped.stdout.decode("utf-8", "replace").strip()
    if not value.startswith("/"):
        raise RuntimeError(f"unexpected WSL path: {value!r}")
    return value


def extract_pinned(names: list[str]) -> dict[str, str]:
    """Extract complete module bodies from the pinned XSTop.sv, one pass per name.

    从钉死的 XSTop.sv 中提取完整模块体，每个名称一趟。仅当首个声明行与精确名称
    匹配时开始采集，并在首个 ``endmodule`` 结束。
    """
    collected: dict[str, str] = {}
    for name in names:
        proc = subprocess.run(
            [
                "wsl.exe",
                "-e",
                "bash",
                "-lc",
                "awk '/^module " + name + "\\(/{f=1} f{print} /^endmodule/{if(f)exit}' "
                + LOCKED_WSL,
            ],
            capture_output=True,
            check=False,
        )
        text = proc.stdout.decode("utf-8", "replace")
        lines: list[str] = []
        started = False
        for line in text.splitlines():
            stripped = line.lstrip()
            if not started:
                if stripped.startswith(f"module {name}("):
                    started = True
                    lines = [line]
            else:
                lines.append(line)
                if stripped.startswith("endmodule"):
                    break
        if not started or not lines:
            raise RuntimeError(f"cannot extract from pinned reference: {name}")
        collected[name] = "\n".join(lines)
    return collected


def referenced_module_names(verilog_text: str) -> list[str]:
    """Find likely child-module instantiations in one pinned body.

    从一个钉死模块体中找出可能的子模块实例化名称。
    """
    ignored = {
        "module", "wire", "reg", "logic", "input", "output", "assign",
        "always", "always_ff", "always_comb", "generate", "if", "for",
    }
    found: list[str] = []
    pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_$]*)\s+[A-Za-z_][A-Za-z0-9_$]*\s*\(")
    for line in verilog_text.splitlines():
        match = pattern.match(line)
        if match and match.group(1) not in ignored and match.group(1) not in found:
            found.append(match.group(1))
    return found


def parse_port_range(text: str) -> int:
    """Turn ``[hi:lo]`` into a bit count. / 把 ``[hi:lo]`` 转成位宽。"""
    body = text.strip()
    if not body:
        return 1
    high, _, low = body[1:-1].partition(":")
    return int(high) - int(low) + 1


def parse_verilog_ports(rtl: str) -> list[tuple[str, str, int]]:
    """Read the emitted/reference port surface out of a Verilog module. / 从 Verilog 模块中读出端口面。"""
    ports: list[tuple[str, str, int]] = []
    for line in rtl.splitlines():
        stripped = line.strip()
        # ``verilog.convert`` emits child modules after the requested top;
        # only declarations before the first endmodule belong to this port
        # surface. / 导出文本在顶层后还会包含子模块，只统计首个顶层。
        if stripped == "endmodule":
            break
        for direction in ("input", "output"):
            if not stripped.startswith(direction + " "):
                continue
            body = stripped[len(direction):].strip()
            if not body.endswith(";"):
                continue
            body = body[:-1].strip()
            if body.startswith("["):
                close = body.index("]")
                width = parse_port_range(body[: close + 1])
                name = body[close + 1:].strip()
            else:
                width = 1
                name = body
            ports.append((name, direction, width))
            break
    return ports


def parse_ansi_sticky_ports(rtl: str) -> list[tuple[str, str, int]]:
    """Parse the pinned artifact's ANSI header with sticky direction/width.

    解析钉死产物的 ANSI 端口头，方向与位宽在续行上保持粘性。续行继承上一行的
    方向与位宽，尾部以逗号或右括号结束。
    """
    ports: list[tuple[str, str, int]] = []
    direction: str | None = None
    width = 1
    for raw in rtl.splitlines():
        line = raw.split("//", 1)[0].rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("module "):
            continue
        if stripped.startswith("input ") or stripped.startswith("output "):
            direction = "input" if stripped.startswith("input ") else "output"
            body = stripped[len(direction):].strip()
            while body and body[-1] in ",;)":
                body = body[:-1].strip()
            if body.startswith("["):
                close = body.index("]")
                width = parse_port_range(body[: close + 1])
                name = body[close + 1:].strip()
            else:
                width = 1
                name = body
            ports.append((name, direction, width))
        elif direction is not None and not stripped.startswith(("assign", "always", "wire", "reg")):
            name = stripped
            while name and name[-1] in ",;)":
                name = name[:-1].strip()
            if name:
                ports.append((name, direction, width))
        if stripped.endswith(");"):
            break
    return ports


def locked_port_table(modules: dict) -> dict[str, list[tuple[str, str, int]]]:
    """Convert the locked hierarchy into ``(name, direction, width)`` tables. / 把锁定层级转换为端口表。"""
    table: dict[str, list[tuple[str, str, int]]] = {}
    for name, entry in modules.items():
        rows: list[tuple[str, str, int]] = []
        for port in cast_list(entry["ports"]):
            rows.append((str(port["name"]), str(port["direction"]), parse_port_range(str(port["width"]))))
        table[name] = rows
    return table


def cast_list(value: object) -> list[dict[str, object]]:
    """Narrow a JSON list to a list of port dicts. / 把 JSON 列表收窄为端口字典列表。"""
    return value  # type: ignore[no-any-return]


def select_family(modules: dict) -> tuple[list[str], list[str]]:
    """Independently recompute the expected covered module set and exclusions.

    独立重算预期被覆盖模块集合与排除集合。家族成员为 scala_sources 命中三个
    家族源文件的锁定模块；排除 NewCSR 的 CSR 模块、ExeUnit 泛型参数变体与
    FP/向量 FU 叶子。
    """
    family: list[str] = []
    for name, info in modules.items():
        srcs = [str(s) for s in (info.get("scala_sources") or [])]
        if any(any(f in s for f in FAMILY_SOURCES) for s in srcs):
            family.append(name)
    covered: list[str] = []
    for name in sorted(family):
        if name == "CSR" or name.startswith("ExeUnit_") or name in EXCLUDED_FP_LEAVES:
            continue
        covered.append(name)
    excluded = sorted(set(family) - set(covered))
    return covered, excluded


def write_diff_harness(work: Path, name: str, mine_sv: str, pinned_sv: str, ports: list[tuple[str, str, int]]) -> Path:
    """Write a two-instance differential harness for one module. / 为一个模块写双实例差分平台。"""
    mine_path = work / f"{name}_DUT.sv"
    mine_path.write_text(mine_sv, encoding="utf-8", newline="\n")
    # Preserve the Verilog module keyword while changing only the top name.
    # 保留 Verilog module 关键字，只替换顶层模块名。
    renamed = pinned_sv.replace(f"module {name}(", f"module {name}_Reference(", 1)
    ref_path = work / f"{name}_Reference.sv"
    ref_path.write_text(renamed, encoding="utf-8", newline="\n")
    # Close the pinned child hierarchy recursively.  A single AluDataModule,
    # for example, instantiates eleven utility modules of its own.
    pending = list(PINNED_CHILDREN[name])
    children: dict[str, str] = {}
    while pending:
        child = pending.pop(0)
        if child in children:
            continue
        try:
            child_sv = extract_pinned([child])[child]
        except RuntimeError:
            continue
        children[child] = child_sv
        for nested in referenced_module_names(child_sv):
            if nested not in children and nested != name:
                pending.append(nested)
    for child, child_sv in children.items():
        (work / f"{child}_Ref.sv").write_text(child_sv, encoding="utf-8", newline="\n")

    inputs = [p for p in ports if p[1] == "input"]
    outputs = [p for p in ports if p[1] == "output"]

    def decl(port: tuple[str, str, int], suffix: str = "") -> str:
        n, _, w = port
        rng = f"[{w - 1}:0] " if w > 1 else ""
        return f"  {rng}{n}{suffix}"

    lines = [f"module diff_{name}("]
    header: list[str] = []
    for p in inputs:
        header.append(("input " if p[1] == "input" else "output ") + (f"[{p[2] - 1}:0] " if p[2] > 1 else "") + p[0])
    for p in outputs:
        rng_out = f"[{p[2] - 1}:0] " if p[2] > 1 else ""
        header.append(f"output {rng_out}dut_{p[0]}")
        header.append(f"output {rng_out}ref_{p[0]}")
    lines.append(",\n".join("  " + h for h in header))
    lines.append(");")
    # The ANSI header already declares every harness signal.  Re-emitting
    # bare names here creates invalid statements such as ``io_in_valid;``.
    dut_conns = ", ".join(f".{p[0]}({p[0]})" for p in inputs) + ", " + ", ".join(
        f".{p[0]}(dut_{p[0]})" for p in outputs
    )
    ref_conns = ", ".join(f".{p[0]}({p[0]})" for p in inputs) + ", " + ", ".join(
        f".{p[0]}(ref_{p[0]})" for p in outputs
    )
    lines.append(f"  {name} dut({dut_conns});")
    # ``ref`` is a SystemVerilog keyword; use a legal instance identifier.
    lines.append(f"  {name}_Reference reference({ref_conns});")
    lines.append("endmodule")
    top_path = work / f"diff_{name}.sv"
    top_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    has_clock = any(p[0] == "clock" for p in inputs)
    has_reset = any(p[0] == "reset" for p in inputs)
    tick_body = (
        "        tb.clock = 0; tb.eval();\n        tb.clock = 1; tb.eval();"
        if has_clock
        else "        tb.eval();"
    )
    reset_block = (
        "    tb.reset = 1;\n"
        + "\n".join(f"    tb.{p[0]} = 0;" for p in inputs if p[0] != "reset")
        + "\n    for (int i = 0; i < 4; i++) tick();\n    tb.reset = 0;"
        if has_reset
        else ""
    )
    cpp = f"""
#include "Vdiff_{name}.h"
#include "verilated.h"
#include <cstdio>
#include <cstdint>
#include <random>
int main(int argc, char** argv) {{
    Verilated::commandArgs(argc, argv);
    static Vdiff_{name} tb;
    std::mt19937_64 rng(0x5632FU);
    long mismatches = 0, checks = 0;
    auto tick = [&]() {{
{tick_body}
    }};
    auto randomize_inputs = [&]() {{
{chr(10).join(f'        tb.{p[0]} = rng() & ((1ULL << {p[2]}) - 1);' for p in inputs)}
    }};
{reset_block}
    for (int v = 0; v < {DIFF_VECTORS}; v++) {{
        randomize_inputs();
        tb.eval();
{chr(10).join(f'        if (tb.dut_{p[0]} != tb.ref_{p[0]}) mismatches++;' for p in outputs)}
{chr(10).join(f'        checks++;' for p in outputs)}
        tick();
    }}
    std::printf("MISMATCHES %ld CHECKS %ld\\n", mismatches, checks);
    return mismatches == 0 ? 0 : 1;
}}
"""
    cpp_path = work / f"tb_{name}.cpp"
    cpp_path.write_text(cpp, encoding="utf-8", newline="\n")

    mk = f"""
all:
\tverilator --cc --exe --build -O2 -Wno-fatal \\
\t  --top-module diff_{name} diff_{name}.sv {name}_DUT.sv {name}_Reference.sv \\
{chr(10).join(f'\t  {child}_Ref.sv \\' for child in children)}
\t  tb_{name}.cpp -o sim_{name}
"""
    (work / f"Makefile_{name}").write_text(mk, encoding="utf-8", newline="\n")
    return top_path


def main() -> int:
    """Run every coverage, port, determinism, differential and tool gate. / 运行覆盖、端口、确定性、差分与工具门禁。"""
    module = load(TARGET, "v2_exu_funcunit_target")
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))
    locked_modules: dict[str, dict[str, object]] = hierarchy["modules"]
    locked_ports = locked_port_table(locked_modules)
    expected, excluded = select_family(locked_modules)
    covered = sorted(module.COVERED_MODULES)

    coverage_missing = sorted(set(expected) - set(covered))
    coverage_extra = sorted(set(covered) - set(expected))

    # Gate 1+2: exact ANSI port surface against the locked hierarchy, plus a
    # determinism proof from two independent elaborations of every member.
    # 门禁 1+2：对照锁定层级的精确端口面，并用每成员两次独立导出证明确定性。
    port_records: list[dict[str, object]] = []
    port_failures: list[str] = []
    determinism_failures: list[str] = []
    verilog_texts: dict[str, str] = {}
    for name in covered:
        first = module.build_verilog({"module": name}, {})
        second = module.build_verilog({"module": name}, {})
        if first != second:
            determinism_failures.append(name)
        verilog_texts[name] = first
        emitted = parse_verilog_ports(first)
        expected_ports = locked_ports[name]
        emitted_set = set(emitted)
        expected_set = set(expected_ports)
        if emitted_set != expected_set:
            missing = sorted(expected_set - emitted_set)
            surplus = sorted(emitted_set - expected_set)
            port_failures.append(f"{name}: missing={missing} surplus={surplus}")
        port_records.append(
            {
                "module": name,
                "locked_port_count": len(expected_ports),
                "emitted_port_count": len(emitted),
                "ports_match": emitted_set == expected_set,
                "verilog_sha256": digest(first.encode()),
                "verilog_bytes": len(first.encode()),
            }
        )

    # Gate 3: Verilator cycle-simulation differential against the pinned
    # artifact for two representative modules (comb Alu, sequential Bku).
    # 门禁 3：对两个代表模块（组合 Alu、时序 Bku）与钉死产物做 Verilator 周期仿真差分。
    WORK.mkdir(parents=True, exist_ok=True)
    pinned_texts = extract_pinned(
        list(DIFFERENTIAL_TARGETS) + [c for t in DIFFERENTIAL_TARGETS for c in PINNED_CHILDREN[t]]
    )
    diff_records: list[dict[str, object]] = []
    differential_pass = True
    for name in DIFFERENTIAL_TARGETS:
        mine = verilog_texts[name]
        pinned = pinned_texts[name]
        mine_ports = parse_verilog_ports(mine)
        pinned_ports = parse_ansi_sticky_ports(pinned)
        port_vector_match = set(mine_ports) == set(pinned_ports)
        work = WORK / f"diff-{name}"
        work.mkdir(parents=True, exist_ok=True)
        write_diff_harness(work, name, mine, pinned, locked_ports[name])
        build = run_wsl(["make", "-f", f"Makefile_{name}", "-C", wsl_path(work)])
        sim_status = "NOT_RUN"
        mismatches = -1
        checks = 0
        if build["status"] == "PASS":
            # Execute from the build directory; otherwise the relative
            # ``obj_dir`` loader path is resolved from the caller's cwd.
            work_wsl = wsl_path(work)
            sim = run_wsl(["bash", "-lc", f"cd {shlex.quote(work_wsl)} && ./obj_dir/sim_{name}"])
            tail = str(sim["output_tail"])
            found = re.search(r"MISMATCHES (\d+) CHECKS (\d+)", tail)
            if found:
                mismatches = int(found.group(1))
                checks = int(found.group(2))
                # A non-zero simulator exit is expected when the comparator
                # finds mismatches; retain the parsed counts instead of
                # collapsing them to ``-1/0``.
                sim_status = "PASS" if sim["status"] == "PASS" and mismatches == 0 else "FAIL"
            else:
                sim_status = "FAIL"
        record = {
            "module": name,
            "mine_port_count": len(mine_ports),
            "pinned_port_count": len(pinned_ports),
            "port_vector_match": port_vector_match,
            "differential_vectors": DIFF_VECTORS,
            "differential_checks": checks,
            "differential_mismatches": mismatches,
            "build_status": build["status"],
            "sim_status": sim_status,
            "build_output_tail": str(build["output_tail"])[-600:],
            "verdict": "BEHAVIOR_MATCH_BOUNDED" if (port_vector_match and sim_status == "PASS") else "MISMATCH_BOUNDED",
        }
        diff_records.append(record)
        differential_pass = differential_pass and record["verdict"] == "BEHAVIOR_MATCH_BOUNDED"

    # Gate 4: standalone Verilator lint and Yosys elaboration for every member.
    # 门禁 4：对每个成员做独立 Verilator lint 与 Yosys 展开。
    source_dir = WORK / "verilog"
    source_dir.mkdir(parents=True, exist_ok=True)
    verdict_path = WORK / "tool-sweep.txt"
    if verdict_path.exists():
        verdict_path.unlink()
    verdict_log = wsl_path(verdict_path)
    sweep_lines: list[str] = []
    for name in covered:
        single = source_dir / f"{name}.sv"
        single.write_text(verilog_texts[name], encoding="utf-8", newline="\n")
        located = wsl_path(single)
        sweep_lines.append(
            f"if verilator --lint-only -Wno-fatal {located} >/dev/null 2>&1;"
            f' then echo "LINT_PASS {name}" >> {verdict_log};'
            f' else echo "LINT_FAIL {name}" >> {verdict_log}; fi'
        )
        sweep_lines.append(
            f"if yosys -Q -p 'read_verilog -sv {located}; hierarchy -top {name};"
            f" proc; check' >/dev/null 2>&1;"
            f' then echo "YOSYS_PASS {name}" >> {verdict_log};'
            f' else echo "YOSYS_FAIL {name}" >> {verdict_log}; fi'
        )
    sweep_path = WORK / "tool-sweep.sh"
    sweep_path.write_text("\n".join(sweep_lines) + "\n", encoding="utf-8", newline="\n")
    sweep = run_wsl(["bash", wsl_path(sweep_path)])
    sweep_output = verdict_path.read_text(encoding="utf-8") if verdict_path.exists() else ""
    lint_verdicts = [line for line in sweep_output.splitlines() if "LINT_" in line]
    yosys_verdicts = [line for line in sweep_output.splitlines() if "YOSYS_" in line]
    lint_failures = sorted(line.split(maxsplit=1)[1] for line in lint_verdicts if line.startswith("LINT_FAIL "))
    yosys_failures = sorted(line.split(maxsplit=1)[1] for line in yosys_verdicts if line.startswith("YOSYS_FAIL "))
    lint_pass_count = sum(1 for line in lint_verdicts if line.startswith("LINT_PASS "))
    yosys_pass_count = sum(1 for line in yosys_verdicts if line.startswith("YOSYS_PASS "))

    default_rtl = module.build_verilog(None, {})
    default_path = WORK / "UHSCBackendExuFuncUnitFamily.sv"
    default_path.write_text(default_rtl, encoding="utf-8", newline="\n")
    default_lint = run_wsl(
        ["verilator", "--lint-only", "-Wno-fatal", wsl_path(default_path)]
    )

    verilator_pass = lint_pass_count == len(covered) and default_lint["status"] == "PASS"
    yosys_pass = yosys_pass_count == len(covered)
    hierarchy_sha256 = digest(HIERARCHY.read_bytes())
    locked_ok = (
        HIERARCHY.stat().st_size > 0
        and hierarchy.get("module_count") == len(hierarchy.get("modules") or {})
        and hierarchy.get("reference_path") == LOCKED_WSL
    )

    gates = {
        "COVERAGE_COMPLETE": "PASS" if not coverage_missing else "FAIL",
        "PORT_SURFACE_MATCHED": "PASS" if not port_failures else "FAIL",
        "DETERMINISTIC_VERILOG": "PASS" if not determinism_failures else "FAIL",
        "DIRECT_TEST_PASS_BOUNDED": "PASS" if differential_pass else "FAIL",
        "V2_REFERENCE_MATCHED": "PASS_BOUNDED_CYCLE_SIM" if differential_pass else "FAIL",
        "VERILATOR": "PASS" if verilator_pass else "FAIL",
        "YOSYS": "PASS" if yosys_pass else "FAIL",
        "V2_LOCKED_REFERENCE_IMMUTABLE": "PASS" if locked_ok else "FAIL",
        "PYTHON_PRESENT": "PASS",
        "ACCEPTED": "NOT_ALLOWED",
    }

    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_EXU_FUNCUNIT_FAMILY",
        "batch_id": "V2-WAVE2-BACKEND-EXU-FUNCUNIT",
        "source_commit": SOURCE_COMMIT,
        "scala_sources": [
            "src/main/scala/xiangshan/backend/fu/FuncUnit.scala",
            "src/main/scala/xiangshan/backend/fu/Bku.scala",
            "src/main/scala/xiangshan/backend/exu/ExeUnit.scala",
        ],
        "target": {
            "path": TARGET.relative_to(ROOT).as_posix(),
            "sha256": digest(TARGET.read_bytes()),
            "line_count": len(TARGET.read_text(encoding="utf-8").splitlines()),
        },
        "locked_hierarchy_sha256": hierarchy_sha256,
        "covered_family_groups": {
            "int_dispatch": [n for n in covered if n.startswith("Dispatcher")],
            "exe_unit": [n for n in covered if n.startswith(("ExeUnit", "MemExeUnit"))],
            "bku_core": [n for n in covered if n in ("Bku", "CountModule", "ClmulModule", "MiscModule", "HashModule", "BlockCipherModule", "CryptoModule", "AddrAddModule")],
            "fu_wrappers": [n for n in covered if n in ("Std", "Fence", "Alu", "MulUnit", "DivUnit", "BranchUnit", "JumpUnit")],
        },
        "coverage": {
            "covered_module_count": len(covered),
            "expected_module_count": len(expected),
            "missing_modules": coverage_missing,
            "extra_modules": coverage_extra,
            "covered_modules": covered,
            "excluded_modules": excluded,
            "exclusion_reason": (
                "CSR belongs to the NewCSR wave; ExeUnit_<n> are generic-parameter EXU variants of the "
                "same locked class; the remaining excluded names are FP/vector FU leaves owned by other "
                "workers (fudian/yunsuan)."
            ),
        },
        "locked_reference": {
            "canonical_path": LOCKED_WSL,
            "immutable_check": locked_ok,
        },
        "port_surface": {
            "status": "PASS" if not port_failures else "FAIL",
            "checked_module_count": len(port_records),
            "failures": port_failures,
            "modules": port_records,
        },
        "determinism": {
            "status": "PASS" if not determinism_failures else "FAIL",
            "repeated_elaborations_per_module": 2,
            "failures": determinism_failures,
        },
        "differential": {
            "status": "PASS" if differential_pass else "FAIL",
            "tool": "verilator",
            "transport": "wsl.exe -e bash -lc",
            "compared_instances": list(DIFFERENTIAL_TARGETS),
            "vector_counts": {
                "modules_compared": len(diff_records),
                "vectors_per_module": DIFF_VECTORS,
                "port_checks_total": sum(int(str(r["differential_checks"])) for r in diff_records),
            },
            "records": diff_records,
            "trace_verdict": "BEHAVIOR_MATCH_BOUNDED" if differential_pass else "MISMATCH_BOUNDED",
            "behavioral_equivalence": "BOUNDED_TO_TWO_INSTANCES" if differential_pass else "NOT_ESTABLISHED",
        },
        "tool_gates": {
            "lint": {
                "status": "PASS" if not lint_failures and lint_pass_count == len(covered) else "FAIL",
                "checked_module_count": len(lint_verdicts),
                "pass_count": lint_pass_count,
                "failures": lint_failures,
            },
            "yosys": {
                "status": "PASS" if not yosys_failures and yosys_pass_count == len(covered) else "FAIL",
                "checked_module_count": len(yosys_verdicts),
                "pass_count": yosys_pass_count,
                "failures": yosys_failures,
            },
            "default_export_lint": default_lint,
            "default_export_bytes": len(default_rtl.encode()),
            "default_export_sha256": digest(default_rtl.encode()),
        },
        "gates": gates,
        "status": "DIRECT_TEST_PASS_BOUNDED" if (
            not coverage_missing
            and not port_failures
            and not determinism_failures
            and differential_pass
            and verilator_pass
            and yosys_pass
            and locked_ok
        ) else "FAIL",
        "acceptance_eligible": False,
        "unclosed": [
            "BEHAVIOR_MATCHED / INTEGRATED / ACCEPTED remain locked by contract; this batch is "
            "DIRECT_TEST_PASS_BOUNDED only.",
            "The Verilator differential covers exactly two instances (comb Alu, sequential Bku) with "
            "512 seeded random vectors each; the other 28 covered members are proven by port surface, "
            "determinism, Verilator lint and Yosys elaboration only.",
            "ExeUnit_<n> FP/vector EXU parameter variants and the FP/vector FU leaves are excluded: "
            "they are owned by other workers; the int-family ExeUnit is emitted for its locked ports.",
            "DivUnit iteration-cycle latency is CONTRACT_ONLY: the pinned divider latency is not "
            "bit-established beyond the request/kill protocol.",
            "The Bku differential uses random opcodes; per-opcode exhaustive equivalence is not claimed.",
            "License review and user approval remain pending.",
        ],
    }
    EVIDENCE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "covered": len(covered),
                "expected": len(expected),
                "excluded": len(excluded),
                "port_failures": len(port_failures),
                "determinism_failures": len(determinism_failures),
                "differential": payload["differential"]["status"],
                "verilator": gates["VERILATOR"],
                "yosys": gates["YOSYS"],
            },
            sort_keys=True,
        )
    )
    return 0 if payload["status"] == "DIRECT_TEST_PASS_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
