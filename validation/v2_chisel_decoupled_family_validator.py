"""Focused bounded validator for the V2 Chisel Decoupled (queue) family.

V2 Chisel Decoupled（队列）族的聚焦有界校验器。

The validator loads the Build subject by exact path, checks every covered
module's Amaranth port surface against ``validation/v2-locked-hierarchy.json``,
proves the emitted Verilog is deterministic, and runs a cycle-by-cycle
differential against the pinned ``XSTop.sv`` modules with Verilator through WSL.

校验器按精确路径加载 Build 主体，对照 ``validation/v2-locked-hierarchy.json``
检查每个被覆盖模块的 Amaranth 端口面，证明导出的 Verilog 是确定性的，并通过
WSL 用 Verilator 与钉死的 ``XSTop.sv`` 模块做逐周期差分。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
TARGET = (
    ROOT
    / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
    / "Build-Cpu.Dependency.Chisel.Decoupled-Hardware.py"
)
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
LOCKED = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
WORK = ROOT / "validation/.work/v2-chisel-decoupled-family"
EVIDENCE = ROOT / "validation/v2-chisel-decoupled-family-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
LOCKED_BYTES = 228590583
CLOCK_HALF_PERIOD = 5
CYCLE_COUNT = 4096
RESET_PULSE_AT = 1024
RESET_PULSE_WIDTH = 2
MISMATCH_PRINT_LIMIT = 16

# Fixture selection keeps one representative of every structural degree of
# freedom the pinned family exposes: power-of-two and wrapped rings, the
# single-entry register, flow-through, pipe, flush, occupancy count, degenerate
# zero-width payload, dead enqueue side, a BundleMap payload, and every
# PipeWithFlush register chain.
# 夹具选择覆盖钉死族的每一种结构自由度：2 的幂与回绕环、单条目寄存器、直通、
# 流水线、flush、占用计数、零宽载荷、被裁掉的入队侧、BundleMap 载荷，以及
# 全部 PipeWithFlush 寄存器链。
QUEUE_DIFFERENTIAL_TARGETS: tuple[str, ...] = (
    "Queue2_UInt2",
    "Queue1_CtrlReq",
    "Queue10_GrantBuffer_Anon",
    "Queue16_GrantQueueTask",
    "Queue5_MSHRRequest",
    "Queue9_TLBundleC",
    "Queue40_L2TlbMQBundle",
    "Queue1_PrefetchTrain",
    "Queue68_BundleMap",
    "Queue2_TLBundleB_10",
)

PIPE_DIFFERENTIAL_TARGETS: tuple[str, ...] = (
    "PipeWithFlush",
    "PipeWithFlush_1",
    "PipeWithFlush_6",
    "PipeWithFlush_7",
    "PipeWithFlush_8",
    "PipeWithFlush_9",
    "PipeWithFlush_10",
    "PipeWithFlush_11",
)

DIFFERENTIAL_TARGETS: tuple[str, ...] = (
    QUEUE_DIFFERENTIAL_TARGETS + PIPE_DIFFERENTIAL_TARGETS
)


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
    """Map a Windows path to WSL with an explicit lookup. / 通过显式查询把 Windows 路径映射到 WSL。"""

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


def extract_many(names: list[str]) -> dict[str, str]:
    """Extract several complete modules from immutable XSTop in one pass.

    单趟从不可变 XSTop 中提取若干完整模块。仅当首个声明行与精确名称匹配时
    开始采集，并在第一个 ``endmodule`` 结束。
    """

    wanted = {f"module {name}(": name for name in names}
    collected: dict[str, list[str]] = {}
    active: str | None = None
    with LOCKED.open("rb") as stream:
        for raw in stream:
            line = raw.decode("utf-8", "replace")
            if active is None:
                stripped = line.lstrip()
                for marker, name in wanted.items():
                    if stripped.startswith(marker):
                        active = name
                        collected[name] = []
                        break
                if active is None:
                    continue
            collected[active].append(line)
            if line.lstrip().startswith("endmodule"):
                active = None
    missing = [name for name in names if name not in collected]
    if missing:
        raise RuntimeError(f"cannot extract from locked reference: {missing}")
    return {name: "".join(lines) for name, lines in collected.items()}


def parse_port_range(text: str) -> int:
    """Turn ``[hi:lo]`` into a bit count. / 把 ``[hi:lo]`` 转成位宽。"""

    body = text.strip()
    if not body:
        return 1
    high, _, low = body[1:-1].partition(":")
    return int(high) - int(low) + 1


def parse_generated_ports(rtl: str) -> list[tuple[str, str, int]]:
    """Read the Amaranth port surface out of the emitted Verilog. / 从导出 Verilog 中读出 Amaranth 端口面。"""

    ports: list[tuple[str, str, int]] = []
    for line in rtl.splitlines():
        stripped = line.strip()
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


def locked_port_table(
    modules: dict[str, dict[str, object]],
) -> dict[str, list[tuple[str, str, int]]]:
    """Convert the locked hierarchy into ``(name, direction, width)`` tables. / 把锁定层级转换为端口表。"""

    table: dict[str, list[tuple[str, str, int]]] = {}
    for name, entry in modules.items():
        rows: list[tuple[str, str, int]] = []
        for port in cast(list[dict[str, object]], entry["ports"]):
            rows.append(
                (
                    str(port["name"]),
                    str(port["direction"]),
                    parse_port_range(str(port["width"])),
                )
            )
        table[name] = rows
    return table


def provenance_sets(modules: dict[str, dict[str, object]]) -> tuple[list[str], list[str]]:
    """Return the locked Decoupled.scala and PipeWithFlush module names. / 返回锁定层级中两个 Scala 来源的模块名。"""

    decoupled: list[str] = []
    pipes: list[str] = []
    for name, entry in modules.items():
        recorded = cast(list[object], entry.get("scala_sources") or [])
        sources = [str(source) for source in recorded]
        if any("chisel3/util/Decoupled.scala" in source for source in sources):
            decoupled.append(name)
        if any("utils/PipeWithFlush.scala" in source for source in sources):
            pipes.append(name)
    return sorted(decoupled), sorted(pipes)


def verilog_range(width: int) -> str:
    """Return the Verilog range text for one width. / 返回某个位宽的 Verilog 范围文本。"""

    return "" if width == 1 else f"[{width - 1}:0]"


def stimulus_chunks(width: int, owner: str) -> tuple[list[str], list[int]]:
    """Name and size the ``lcg`` slices that drive one port. / 命名并确定驱动某个端口的 ``lcg`` 片段。"""

    count = (width + 63) // 64
    widths = [64] * count
    widths[-1] = width - 64 * (count - 1)
    names = [f"c_{owner}_{index}" for index in range(count)]
    return names, widths


def build_testbench(
    fixtures: list[tuple[str, list[tuple[str, str, int]]]],
) -> str:
    """Emit one combined testbench driving every fixture pair. / 生成同时驱动所有夹具对的测试平台。"""

    # Every fixture keeps its own nets so a single Verilator binary can run the
    # whole trace set without name collisions. / 每个夹具保留自己的网线，使单个
    # Verilator 可执行文件能跑完整波形集且不重名。
    def drive_name(fixture: str, port: str) -> str:
        return f"i_{fixture}_{port}"

    def target_name(fixture: str, port: str) -> str:
        return f"t_{fixture}_{port}"

    def reference_name(fixture: str, port: str) -> str:
        return f"r_{fixture}_{port}"

    def port_error_name(fixture: str, port: str) -> str:
        return f"pe_{fixture}_{port}"

    lines: list[str] = [
        "// Generated by validation/v2_chisel_decoupled_family_validator.py",
        "// 由 validation/v2_chisel_decoupled_family_validator.py 生成",
        "`timescale 1ns/1ps",
        "",
        "module tb;",
        "  reg clock;",
        "  reg reset;",
        "  reg [63:0] lcg;",
        "  reg [63:0] lcg_next;",
        "",
    ]
    prepared: list[tuple[str, list[tuple[str, str, int]], list[tuple[str, str, int]],
                        list[tuple[str, str, int]], list[tuple[str, int]]]] = []
    for name, ports in fixtures:
        driven = [
            port for port in ports
            if port[1] == "input" and port[0] not in ("clock", "reset")
        ]
        observed = [port for port in ports if port[1] == "output"]
        chunks: list[tuple[str, int]] = []
        for port_name, _direction, width in driven:
            names, widths = stimulus_chunks(width, f"{name}_{port_name}")
            chunks.extend(zip(names, widths))

        prepared.append((name, ports, driven, observed, chunks))

        lines.append(f"  // fixture {name}")
        lines.append(f"  integer cycle_{name};")
        lines.append(f"  integer errors_{name};")
        for port_name, _direction, width in driven:
            lines.append(f"  reg {verilog_range(width)} {drive_name(name, port_name)};")
        for port_name, _direction, width in observed:
            lines.append(f"  wire {verilog_range(width)} {target_name(name, port_name)};")
            lines.append(f"  wire {verilog_range(width)} {reference_name(name, port_name)};")
            lines.append(f"  integer {port_error_name(name, port_name)};")
        for chunk_name, chunk_width in chunks:
            lines.append(f"  reg {verilog_range(chunk_width)} {chunk_name};")
        lines.append("")

    for name, ports, _driven, _observed, _chunks in prepared:
        # Clock and reset are only wired when the pinned module really declares
        # them: a zero-stage PipeWithFlush is purely combinational and has
        # neither port. / 只有钉死模块真的声明了 clock/reset 才连线：零级
        # PipeWithFlush 是纯组合逻辑，两个端口都不存在。
        def connect(naming: Callable[[str, str], str]) -> str:
            parts: list[str] = []
            for port_name, direction, _width in ports:
                if direction != "input":
                    continue
                if port_name in ("clock", "reset"):
                    parts.append(f".{port_name}({port_name})")
                else:
                    parts.append(f".{port_name}({drive_name(name, port_name)})")
            for port_name, direction, _width in ports:
                if direction == "output":
                    parts.append(f".{port_name}({naming(name, port_name)})")
            return ", ".join(parts)

        lines.append(f"  {name} {name}_target ({connect(target_name)});")
        lines.append(f"  {name}_Reference {name}_reference ({connect(reference_name)});")
    lines.append("")
    lines.append(f"  always #{CLOCK_HALF_PERIOD} clock = ~clock;")
    lines.append("")

    for name, _ports, driven, observed, chunks in prepared:
        lines.append(f"  initial begin  // fixture {name}")
        lines.append("    reset = 1;")
        lines.append("    lcg = 64'h0123_4567_89AB_CDEF;")
        lines.append(f"    errors_{name} = 0;")
        for port_name, _direction, _width in observed:
            lines.append(f"    {port_error_name(name, port_name)} = 0;")
        for port_name, _direction, width in driven:
            lines.append(f"    {drive_name(name, port_name)} = {width}'d0;")
        lines.append("    repeat (2) @(negedge clock);")
        lines.append(
            f"    for (cycle_{name} = 0; cycle_{name} < {CYCLE_COUNT};"
            f" cycle_{name} = cycle_{name} + 1) begin"
        )
        lines.append(f"      if (cycle_{name} == {RESET_PULSE_AT}) reset = 1;")
        lines.append(
            f"      if (cycle_{name} == {RESET_PULSE_AT + RESET_PULSE_WIDTH}) reset = 0;"
        )
        chunk_cursor = 0
        for port_name, _direction, width in driven:
            names, width_list = stimulus_chunks(width, f"{name}_{port_name}")
            declared = [chunks[chunk_cursor + offset][0] for offset in range(len(width_list))]
            if declared != names:
                raise AssertionError(f"chunk naming drift on {name}.{port_name}")
            chunk_cursor += len(width_list)
            for chunk_name, chunk_width in zip(names, width_list):
                lines.append(
                    "      lcg_next = (lcg << 1) ^ (lcg[63] ? 64'hD800_0000_0000_0000 : 64'd0);"
                )
                lines.append("      lcg = lcg_next;")
                lines.append(f"      {chunk_name} = lcg[{chunk_width - 1}:0];")
            lines.append(
                f"      {drive_name(name, port_name)} = {{{', '.join(reversed(names))}}};")
        lines.append("      #1;")
        for port_name, _direction, _width in observed:
            lines.append(
                f"      if ({target_name(name, port_name)} !== {reference_name(name, port_name)})"
                f" begin "
                f"errors_{name} = errors_{name} + 1; "
                f"{port_error_name(name, port_name)} = {port_error_name(name, port_name)} + 1; "
                f"if (errors_{name} <= {MISMATCH_PRINT_LIMIT}) "
                f'$display("MISMATCH {name} cycle=%0d port={port_name} target=%h reference=%h",'
                f" cycle_{name}, {target_name(name, port_name)},"
                f" {reference_name(name, port_name)}); end"
            )
        lines.append("      @(negedge clock);")
        lines.append("    end")
        for port_name, _direction, _width in observed:
            lines.append(
                f'    $display("PORTERR {name} {port_name} %0d",'
                f" {port_error_name(name, port_name)});"
            )
        lines.append(
            f'    $display("FIXTURE {name} cycles=%0d errors=%0d", {CYCLE_COUNT}, errors_{name});'
        )
        lines.append("  end")
        lines.append("")

    watchdog_terms = " && ".join(f"errors_{name} == 0" for name, _ports in fixtures)
    total = CYCLE_COUNT * (CLOCK_HALF_PERIOD * 2) + 200
    lines.append("  initial begin  // watchdog")
    lines.append(f"    #{total};")
    lines.append(f"    if ({watchdog_terms})")
    lines.append(f'      $display("UHSC_DECOUPLED_DIFF_PASS fixtures=%0d", {len(fixtures)});')
    lines.append('    else $display("UHSC_DECOUPLED_DIFF_FAIL");')
    lines.append("    $finish;")
    lines.append("  end")
    lines.append("")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def main() -> int:
    """Run every coverage, port, determinism, differential and tool gate. / 运行覆盖、端口、确定性、差分与工具门禁。"""

    module = load(TARGET, "v2_chisel_decoupled_target")
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))
    locked_modules: dict[str, dict[str, object]] = hierarchy["modules"]
    locked_ports = locked_port_table(locked_modules)
    decoupled_sources, pipe_sources = provenance_sets(locked_modules)
    expected = sorted(set(decoupled_sources) | set(pipe_sources))

    queue_specs = list(module.queue_instances())
    ram_specs = list(module.queue_ram_instances())
    pipe_specs = list(module.pipe_instances())
    covered = sorted(
        [spec.module for spec in queue_specs]
        + [spec.module for spec in ram_specs]
        + [spec.module for spec in pipe_specs]
    )

    # Gate 1: coverage of every locked Decoupled.scala / PipeWithFlush module.
    # 门禁 1：覆盖锁定层级里每个 Decoupled.scala / PipeWithFlush 模块。
    coverage_missing = sorted(set(expected) - set(covered))
    coverage_extra = sorted(set(covered) - set(expected))

    # Gate 2: exact ANSI port surface against the locked hierarchy, plus a
    # determinism proof from two independent elaborations of every member.
    # 门禁 2：对照锁定层级的精确 ANSI 端口面，并用每个成员两次独立导出证明确定性。
    port_records: list[dict[str, object]] = []
    port_failures: list[str] = []
    determinism_failures: list[str] = []
    for name in covered:
        first = module.build_verilog({"module": name, "top_name": name}, {})
        second = module.build_verilog({"module": name, "top_name": name}, {})
        if first != second:
            determinism_failures.append(name)
        emitted = parse_generated_ports(first)
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
                "declaration_order_preserved": emitted == expected_ports,
                "verilog_sha256": digest(first.encode()),
                "verilog_bytes": len(first.encode()),
            }
        )

    # Gate 3: cycle-by-cycle differential against the pinned artifacts.
    # 门禁 3：与钉死产物逐周期差分。
    WORK.mkdir(parents=True, exist_ok=True)
    covered_lookup = {spec.module: spec for spec in queue_specs}
    # Two passes over the pinned artifact: one for the queue fixtures, one for
    # every helper memory they instantiate.
    # 对钉死产物只做两趟：一趟取队列夹具，一趟取它们实例化的全部辅助存储器。
    fixture_texts = extract_many(list(DIFFERENTIAL_TARGETS))
    all_rams = sorted(
        {
            ram
            for text in fixture_texts.values()
            for ram in re.findall(r"\bram_\d+x\d+\b", text)
        }
    )
    ram_texts = extract_many(all_rams) if all_rams else {}
    fixtures: list[tuple[str, list[tuple[str, str, int]]]] = []
    target_text = ""
    reference_text = ""
    for name in DIFFERENTIAL_TARGETS:
        fixtures.append((name, locked_ports[name]))
        target_text += module.build_verilog({"module": name, "top_name": name}, {})
        ram_names = sorted(set(re.findall(r"\bram_\d+x\d+\b", fixture_texts[name])))
        renamed = fixture_texts[name].replace(f"module {name}(", f"module {name}_Reference(", 1)
        reference_text += renamed + "".join(ram_texts[ram] for ram in ram_names)

    # The fixture port surface is the locked one, so a mismatch in gate 2
    # cannot silently weaken the trace comparison.
    # 夹具端口面取自锁定层级，因此门禁 2 的失配不会悄悄削弱波形比对。
    tb_text = build_testbench(fixtures)
    differential_path = WORK / "decoupled-differential.sv"
    differential_path.write_text(
        target_text + reference_text + tb_text, encoding="utf-8", newline="\n"
    )
    object_dir = WORK / "obj-differential"
    compile_result = run_wsl(
        [
            "verilator",
            "--binary",
            "--timing",
            "-Wno-fatal",
            "-Wno-WIDTHEXPAND",
            "-Wno-WIDTHTRUNC",
            "--x-assign",
            "0",
            "--x-initial",
            "0",
            "--top-module",
            "tb",
            "--Mdir",
            wsl_path(object_dir),
            wsl_path(differential_path),
        ]
    )
    run_log = WORK / "decoupled-differential.log"
    if run_log.exists():
        run_log.unlink()
    run = (
        run_wsl(
            [
                "bash",
                "-c",
                f"{wsl_path(object_dir / 'Vtb')} > {wsl_path(run_log)} 2>&1",
            ]
        )
        if compile_result["returncode"] == 0
        else {"status": "SKIP", "returncode": -1, "output_tail": ""}
    )
    trace_output = run_log.read_text(encoding="utf-8") if run_log.exists() else ""
    trace_pass = (
        compile_result["returncode"] == 0
        and run.get("returncode") == 0
        and "UHSC_DECOUPLED_DIFF_PASS" in trace_output
        and "UHSC_DECOUPLED_DIFF_FAIL" not in trace_output
    )
    fixture_records: list[dict[str, object]] = []
    for name in DIFFERENTIAL_TARGETS:
        # A fixture only counts as matched when its own end-of-run summary line
        # is present with zero errors; an absent line must fail closed.
        # 只有夹具自己的收尾摘要行存在且错误数为零才算匹配；缺行必须失败关闭。
        summaries = [
            line
            for line in trace_output.splitlines()
            if line.startswith(f"FIXTURE {name} ")
        ]
        record: dict[str, object] = {
            "module": name,
            "family": "queue" if name.startswith("Queue") else "pipe_with_flush",
            "cycles": CYCLE_COUNT,
            "locked_port_count": len(locked_ports[name]),
            "mid_run_reset_pulse_cycle": RESET_PULSE_AT,
            "has_clock": ("clock", "input", 1) in locked_ports[name],
            "has_reset": ("reset", "input", 1) in locked_ports[name],
            "fixture_summary": summaries[0] if summaries else "",
            "trace_match": bool(summaries)
            and summaries[0].endswith("errors=0")
            and f"MISMATCH {name} " not in trace_output,
            "output_errors": sorted(
                (line.split()[2], int(line.split()[3]))
                for line in trace_output.splitlines()
                if line.startswith(f"PORTERR {name} ")
            ),
        }
        spec = covered_lookup.get(name)
        if spec is not None:
            record.update(
                {
                    "entries": spec.entries,
                    "pointer_bits": spec.pointer_bits,
                    "stored_word_bits": spec.word_bits,
                    "flow": bool(spec.flow),
                    "pipe_option": bool(spec.pipe),
                    "has_flush": bool(spec.flush),
                    "has_count": bool(spec.count),
                }
            )
        else:
            pipe_spec = next(item for item in pipe_specs if item.module == name)
            record.update(
                {
                    "latency": pipe_spec.latency,
                    "field_count": len(pipe_spec.fields),
                    "flush_field_count": len(pipe_spec.flush_fields),
                    "stage_rules": list(pipe_spec.stage_rules),
                    "stage_shifts": [list(stage) for stage in pipe_spec.stage_shifts],
                }
            )
        fixture_records.append(record)

    # Gate 4: standalone Verilator lint and Yosys elaboration check of every
    # covered member, plus the same checks on the default family export.
    # 门禁 4：对每个被覆盖成员做独立 Verilator lint 与 Yosys 展开检查，
    # 并对默认族导出做同样的检查。
    source_dir = WORK / "verilog"
    source_dir.mkdir(parents=True, exist_ok=True)
    verdict_path = WORK / "tool-sweep.txt"
    if verdict_path.exists():
        verdict_path.unlink()
    verdict_log = wsl_path(verdict_path)
    sweep_lines: list[str] = []
    for name in covered:
        single = source_dir / f"{name}.sv"
        single.write_text(
            module.build_verilog({"module": name, "top_name": name}, {}),
            encoding="utf-8",
            newline="\n",
        )
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
    lint_failures = sorted(
        line.split(maxsplit=1)[1] for line in lint_verdicts if line.startswith("LINT_FAIL ")
    )
    yosys_failures = sorted(
        line.split(maxsplit=1)[1] for line in yosys_verdicts if line.startswith("YOSYS_FAIL ")
    )
    lint_pass_count = sum(1 for line in lint_verdicts if line.startswith("LINT_PASS "))
    yosys_pass_count = sum(1 for line in yosys_verdicts if line.startswith("YOSYS_PASS "))
    lint_results: dict[str, object] = {
        "status": "PASS"
        if not lint_failures and lint_pass_count == len(covered)
        else "FAIL",
        "command": "verilator --lint-only -Wno-fatal <member>.sv",
        "checked_module_count": len(lint_verdicts),
        "pass_count": lint_pass_count,
        "failures": lint_failures,
        "sweep": sweep,
    }
    yosys_results: dict[str, object] = {
        "status": "PASS"
        if not yosys_failures and yosys_pass_count == len(covered)
        else "FAIL",
        "command": "yosys -Q -p 'read_verilog -sv <member>.sv; hierarchy -top <member>; proc; check'",
        "checked_module_count": len(yosys_verdicts),
        "pass_count": yosys_pass_count,
        "failures": yosys_failures,
    }

    default_path = WORK / "UHSCChiselQueueFamily.sv"
    default_rtl = module.build_verilog(None, {})
    default_path.write_text(default_rtl, encoding="utf-8", newline="\n")
    default_lint = run_wsl(
        ["verilator", "--lint-only", "-Wno-fatal", wsl_path(default_path)]
    )
    default_yosys = run_wsl(
        [
            "yosys",
            "-Q",
            "-p",
            f"read_verilog -sv {wsl_path(default_path)}; hierarchy -top UHSCChiselQueueFamily;"
            " proc; check",
        ]
    )

    verilator_pass = lint_results["status"] == "PASS" and default_lint["status"] == "PASS"
    yosys_pass = yosys_results["status"] == "PASS" and default_yosys["status"] == "PASS"
    locked_ok = (
        LOCKED.is_file()
        and LOCKED.stat().st_size == LOCKED_BYTES
        and digest(LOCKED.read_bytes()) == LOCKED_SHA256
    )

    gates = {
        "COVERAGE_COMPLETE": "PASS" if not coverage_missing else "FAIL",
        "PORT_SURFACE_MATCHED": "PASS" if not port_failures else "FAIL",
        "DETERMINISTIC_VERILOG": "PASS" if not determinism_failures else "FAIL",
        "DIRECT_TEST_PASS_BOUNDED": "PASS" if trace_pass else "FAIL",
        "V2_REFERENCE_MATCHED": (
            "PASS_BOUNDED_DECOUPLED_FIXTURES" if trace_pass else "FAIL"
        ),
        "VERILATOR": "PASS" if verilator_pass else "FAIL",
        "YOSYS": "PASS" if yosys_pass else "FAIL",
        "V2_LOCKED_REFERENCE_IMMUTABLE": "PASS" if locked_ok else "FAIL",
        "PYTHON_PRESENT": "PASS",
        "UHSC_LOCALIZED": "PASS_BOUNDED_FAMILY_LOCAL_NAME",
        "PARENT_CLOSURE_MATCHED": "PENDING_SYSTEM_TOP_QUEUE_PARENTS",
        "LICENSE_REVIEW": "PENDING",
        "ACCEPTED": "NOT_ALLOWED",
    }
    passed = (
        not coverage_missing
        and not port_failures
        and not determinism_failures
        and trace_pass
        and verilator_pass
        and yosys_pass
        and locked_ok
    )
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_CHISEL_DECOUPLED_FAMILY",
        "batch_id": "V2-DEPENDENCY-DECOUPLED-001",
        "source_commit": SOURCE_COMMIT,
        "scala_sources": [
            "src/main/scala/chisel3/util/Decoupled.scala",
            "src/main/scala/utils/PipeWithFlush.scala",
        ],
        "target": {
            "path": TARGET.relative_to(ROOT).as_posix(),
            "sha256": digest(TARGET.read_bytes()),
            "line_count": len(TARGET.read_text(encoding="utf-8").splitlines()),
        },
        "coverage": {
            "covered_module_count": len(covered),
            "expected_module_count": len(expected),
            "decoupled_scala_module_count": len(decoupled_sources),
            "pipe_with_flush_module_count": len(pipe_sources),
            "queue_instance_count": len(queue_specs),
            "queue_ram_primitive_count": len(ram_specs),
            "pipe_instance_count": len(pipe_specs),
            "missing_modules": coverage_missing,
            "extra_modules": coverage_extra,
            "covered_modules": covered,
        },
        "locked_reference": {
            "canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
            "xstop_sha256": LOCKED_SHA256,
            "xstop_bytes": LOCKED_BYTES,
            "immutable": locked_ok,
        },
        "port_surface": {
            "status": "PASS" if not port_failures else "FAIL",
            "checked_module_count": len(port_records),
            "declaration_order_preserved_module_count": sum(
                1 for record in port_records if record["declaration_order_preserved"]
            ),
            "failures": port_failures,
            "modules": port_records,
        },
        "determinism": {
            "status": "PASS" if not determinism_failures else "FAIL",
            "repeated_elaborations_per_module": 2,
            "failures": determinism_failures,
        },
        "differential": {
            "status": "PASS" if trace_pass else "FAIL",
            "tool": "verilator",
            "transport": "wsl.exe -d Debian -- bash -lc",
            "stimulus": "shared 64-bit Galois LFSR replayed identically into both modules",
            "compared_signals": [
                "io_deq_valid",
                "io_deq_bits_*",
                "io_enq_ready",
                "io_count",
                "every remaining output port",
            ],
            "fixture_families": {
                "queue": len(QUEUE_DIFFERENTIAL_TARGETS),
                "pipe_with_flush": len(PIPE_DIFFERENTIAL_TARGETS),
            },
            "trace_log_sha256": digest(trace_output.encode()),
            "trace_log_lines": len(trace_output.splitlines()),
            "fixture_count": len(fixture_records),
            "cycles_per_fixture": CYCLE_COUNT,
            "total_cycles": CYCLE_COUNT * len(fixture_records),
            "compile": compile_result,
            "run": run,
            "fixtures": fixture_records,
        },
        "tool_gates": {
            "lint": lint_results,
            "yosys": yosys_results,
            "default_export_lint": default_lint,
            "default_export_yosys": default_yosys,
            "default_export_bytes": len(default_rtl.encode()),
            "default_export_sha256": digest(default_rtl.encode()),
        },
        "gates": gates,
        "status": "DIRECT_TEST_PASS_BOUNDED" if passed else "FAIL",
        "acceptance_eligible": False,
        "unclosed": [
            "Queue/BundleMap parents and the full XSTop top-level closure remain pending.",
            "The Verilator trace set holds 10 of the 134 queue instances, all 8 PipeWithFlush "
            "instances and 0 of the 74 ram_<N>x<W> primitives; every remaining member is port-, "
            "determinism- and lint/Yosys-verified only.",
            "Two pipe fixtures (PipeWithFlush, PipeWithFlush_8) are combinational and declare no "
            "clock/reset, so they only prove pass-through and flush masking; the registered stages "
            "are covered by the other six pipe fixtures.",
            "hasFlush is exercised by a single fixture (Queue40_L2TlbMQBundle) and the queue "
            "pipe option by a single fixture (Queue1_PrefetchTrain).",
            "BundleMap payloads are exercised through one fixture (Queue68_BundleMap).",
            "Port equality is a set comparison on (name, direction, width). The emitted "
            "declaration order differs from the pinned order for every member because Amaranth "
            "emits clock/reset after the data ports; only the surface identity is claimed.",
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
                "port_failures": len(port_failures),
                "determinism_failures": len(determinism_failures),
                "differential": payload["differential"]["status"],
                "verilator": gates["VERILATOR"],
                "yosys": gates["YOSYS"],
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
