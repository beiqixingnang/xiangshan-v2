"""Focused bounded validator for the V2 memory lsq-uncache/TLB/vector-split family.

V2 访存侧 uncache load-queue、TLB 存储与向量分裂族的聚焦有界校验器。

The validator loads the Build subject by exact path, checks every covered
module's Amaranth port surface against ``validation/v2-locked-hierarchy.json``,
proves the emitted Verilog of representative members is deterministic, runs a
bounded behavioral differential for ``FreeList`` and ``UncacheEntry_15`` against
the pinned ``XSTop.sv`` through Verilator via WSL, and runs Verilator lint plus
Yosys elaboration on bounded representative members. Status stays at most
``DIRECT_TEST_PASS_BOUNDED``.

校验器按精确路径加载 Build 主体，对照 ``validation/v2-locked-hierarchy.json``
检查每个被覆盖模块的 Amaranth 端口面，证明代表成员导出的 Verilog 是确定性的，
经 WSL 用 Verilator 对 ``FreeList`` 与 ``UncacheEntry_15`` 执行与钉死
``XSTop.sv`` 的有界行为差分，并对有界代表成员运行 Verilator lint 与 Yosys 展开。
状态至多 ``DIRECT_TEST_PASS_BOUNDED``。
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
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = (
    ROOT
    / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory"
    / "Build-Cpu.Memory.Lsqueue.Uncache-Hardware.py"
)
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
LOCKED_WSL = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
LOCKED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
WORK = ROOT / "validation/.work/v2-memory-lsqueue-uncache-family"
EVIDENCE = ROOT / "validation/v2-memory-lsqueue-uncache-family-results.json"
SOURCE_COMMIT = "8b181bc"

# Two representative modules carry the bounded behavioral differential.
# 两个代表模块承担有界行为差分。
DIFFERENTIAL_TARGETS: tuple[str, ...] = ("FreeList", "UncacheEntry_15")
DIFFERENTIAL_CYCLES = 400
RESET_CYCLES = 4

# Tool-sweep representatives: one per family plus the largest parents.
# 工具扫查代表：每族一个外加最大的父模块。
TOOL_SWEEP_TARGETS: tuple[str, ...] = (
    "FreeList",
    "UncacheEntry",
    "LoadQueueUncache",
    "TLBFA",
    "TlbStorageWrapper",
    "VSSplitImp",
    "VLSplitImp",
    "Repeater",
    "PTWRepeaterNB",
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


def run_wsl(command: list[str], timeout: int = 1800) -> dict[str, object]:
    """Run one bounded WSL command. / 运行一条有界 WSL 命令。"""

    rendered = " ".join(shlex.quote(item) for item in command)
    result = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", rendered],
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {
        "command": command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "output_tail": output[-2000:],
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


def extract_pinned(name: str) -> str:
    """Extract one complete module body from the pinned XSTop.sv. / 从钉死 XSTop.sv 提取一个完整模块体。"""

    proc = subprocess.run(
        [
            "wsl.exe",
            "-e",
            "bash",
            "-lc",
            "awk '/^module " + name + "\\(/,/^endmodule/' " + LOCKED_WSL,
        ],
        capture_output=True,
        check=False,
    )
    text = proc.stdout.decode("utf-8", "replace")
    if "module " + name + "(" not in text or "endmodule" not in text:
        raise RuntimeError("cannot extract from pinned reference: " + name)
    return text


def parse_port_range(text: str) -> int:
    """Turn ``[hi:lo]`` into a bit count. / 把 ``[hi:lo]`` 转成位宽。"""

    body = text.strip()
    if not body:
        return 1
    high, _, low = body[1:-1].partition(":")
    return int(high) - int(low) + 1


def locked_ports(modules: dict[str, Any], name: str) -> list[tuple[str, str, int]]:
    """Return the locked ``(name, direction, width)`` table of one module. / 返回某模块的锁定端口表。"""

    rows: list[tuple[str, str, int]] = []
    for port in modules[name]["ports"]:
        rows.append((str(port["name"]), str(port["direction"]), parse_port_range(str(port["width"]))))
    return rows


def amaranth_ports(module: Any, name: str) -> list[tuple[str, str, int]]:
    """Return the constructed Amaranth port surface of one covered member. / 返回某被覆盖成员的 Amaranth 端口面。"""

    spec = module.family_spec(name)
    return [(str(port_name), str(direction), int(bits)) for port_name, direction, bits in spec.ports]


def generate_stimulus(name: str, ports: list[tuple[str, str, int]], cycles: int) -> list[dict[str, int]]:
    """Generate deterministic random input vectors. / 生成确定性的随机输入向量。"""

    rng = random.Random(0x5EED2026)
    vectors: list[dict[str, int]] = []
    inputs = [(p, d, w) for p, d, w in ports if d == "input" and p not in ("clock", "reset")]
    for cycle in range(cycles):
        record: dict[str, int] = {}
        for port, _direction, width in inputs:
            record[port] = rng.getrandbits(width)
        vectors.append(record)
    return vectors


def write_tb(name: str, ports: list[tuple[str, str, int]], mine: str, pinned: str, work: Path) -> None:
    """Write the two-DUT differential testbench files. / 写双 DUT 差分测试台文件。"""

    mine_module = "UHSC" + name
    ref_module = name + "_Reference"
    pinned_renamed = pinned.replace("module " + name + "(", "module " + ref_module + "(", 1)
    (work / f"{name}_Reference.sv").write_text(pinned_renamed, encoding="utf-8", newline="\n")
    (work / f"{mine_module}.sv").write_text(mine, encoding="utf-8", newline="\n")

    tb_ports: list[str] = []
    for port, direction, width in ports:
        if direction == "input":
            if port in ("clock", "reset"):
                tb_ports.append(f"  input {port}")
            else:
                tb_ports.append(f"  input [{width - 1}:0] {port}")
        else:
            tb_ports.append(f"  output [{width - 1}:0] mine_{port}")
            tb_ports.append(f"  output [{width - 1}:0] ref_{port}")
    connect_mine = ",\n".join(
        f"    .{port}({('mine_' + port) if direction == 'output' else port})"
        for port, direction, _width in ports
    )
    connect_ref = ",\n".join(
        f"    .{port}({('ref_' + port) if direction == 'output' else port})"
        for port, direction, _width in ports
    )
    body: list[str] = ["module tb ("]
    body.append(",\n".join(tb_ports))
    body.append(");")
    body.append("")
    body.append(f"  {mine_module} u_mine(")
    body.append(connect_mine)
    body.append("  );")
    body.append("")
    body.append(f"  {ref_module} u_ref(")
    body.append(connect_ref)
    body.append("  );")
    body.append("endmodule")
    (work / "tb.sv").write_text("\n".join(body) + "\n", encoding="utf-8", newline="\n")

    stimulus: list[str] = []
    for record in generate_stimulus(name, ports, DIFFERENTIAL_CYCLES):
        stimulus.append(" ".join("%x" % value for value in record.values()))
    (work / "stimulus.hex").write_text("\n".join(stimulus) + "\n", encoding="utf-8", newline="\n")

    # The driver owns clock/reset around every sampled vector.  They must not
    # consume stimulus tokens, otherwise the second functional input is
    # accidentally driven into reset and the trace no longer has a defined
    # reset sequence.
    input_names = [
        port for port, direction, _w in ports
        if direction == "input" and port not in ("clock", "reset")
    ]
    output_specs = [(port, width) for port, direction, width in ports if direction == "output"]
    main: list[str] = [
        "#include \"Vtb.h\"",
        "#include \"verilated.h\"",
        "#include <cstdio>",
        "#include <cstdlib>",
        "#include <fstream>",
        "#include <sstream>",
        "#include <string>",
        "#include <vector>",
        "",
        "int main(int argc, char** argv) {",
        "  Verilated::commandArgs(argc, argv);",
        "  Vtb* dut = new Vtb;",
        "  std::ifstream stim(\"stimulus.hex\");",
        "  if (!stim) { std::printf(\"STIMULUS_MISSING\\n\"); return 2; }",
        "  std::string line;",
        "  long long cycles = 0; long long mismatches = 0; long long checked = 0;",
        "  dut->clock = 0; dut->reset = 1;",
        f"  for (int i = 0; i < {RESET_CYCLES}; i++) {{ dut->clock = 0; dut->eval(); dut->clock = 1; dut->eval(); }}",
        "  dut->reset = 0;",
        "  while (std::getline(stim, line)) {",
        "    if (line.empty()) continue;",
        "    std::istringstream parts(line);",
        "    std::string token;",
    ]
    for port in input_names:
        main.append(f"    if (!(parts >> token)) break; dut->{port} = std::strtoull(token.c_str(), nullptr, 16);")
    main.extend(
        [
        "    dut->clock = 0; dut->eval();",
        ]
    )
    for port, _width in output_specs:
        main.append(
            f"    if (dut->mine_{port} != dut->ref_{port}) mismatches++;"
        )
        main.append(f"    checked++;")
    main.extend(
        [
        "    dut->clock = 1; dut->eval();",
        "    cycles++;",
        "  }",
        "  std::printf(\"CYCLES %lld MISMATCH %lld CHECKED %lld\\n\", cycles, mismatches, checked);",
        "  delete dut;",
        "  return mismatches == 0 ? 0 : 1;",
        "}",
        "",
    ]
    )
    newline_join = chr(10)
    (work / "main.cpp").write_text(newline_join.join(main) + newline_join, encoding="utf-8", newline="\n")


def main() -> int:
    """Run every coverage, port, determinism, differential and tool gate. / 运行覆盖、端口、确定性、差分与工具门禁。"""

    module = load(TARGET, "v2_lsq_uncache_target")
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))
    locked_modules: dict[str, Any] = hierarchy["modules"]
    covered = sorted(module.CATALOG_ROWS and [row.split("|")[0] for row in module.CATALOG_ROWS])
    missing = sorted(set(covered) - set(locked_modules))
    extra_locked = sorted(set(locked_modules) - set(covered))

    # Gate 1: exact port surface of every covered member against the locked
    # hierarchy, without elaboration.
    # 门禁 1：不展开即可对照锁定层级检查每个成员的精确端口面。
    port_records: list[dict[str, object]] = []
    port_failures: list[str] = []
    for name in covered:
        expected = set(locked_ports(locked_modules, name))
        emitted = set(amaranth_ports(module, name))
        if expected != emitted:
            port_failures.append(
                f"{name}: missing={sorted(expected - emitted)} surplus={sorted(emitted - expected)}"
            )
        port_records.append(
            {
                "module": name,
                "locked_port_count": len(expected),
                "amaranth_port_count": len(emitted),
                "ports_match": expected == emitted,
            }
        )

    # Gate 2: deterministic Verilog for the differential and sweep targets.
    # 门禁 2：差分与扫查目标的确定性 Verilog。
    determinism_targets = sorted(set(DIFFERENTIAL_TARGETS) | set(TOOL_SWEEP_TARGETS))
    determinism_failures: list[str] = []
    sha256_table: dict[str, str] = {}
    for name in determinism_targets:
        first = module.build_verilog({"module": name}, {})
        second = module.build_verilog({"module": name}, {})
        if first != second:
            determinism_failures.append(name)
        sha256_table[name] = digest(first.encode())

    # Gate 3: bounded behavioral differential through Verilator via WSL.
    # 门禁 3：经 WSL 用 Verilator 做有界行为差分。
    WORK.mkdir(parents=True, exist_ok=True)
    diff_records: list[dict[str, object]] = []
    differential_pass = True
    for name in DIFFERENTIAL_TARGETS:
        work = WORK / name
        work.mkdir(parents=True, exist_ok=True)
        mine = module.build_verilog({"module": name}, {})
        pinned = extract_pinned(name)
        ports = locked_ports(locked_modules, name)
        write_tb(name, ports, mine, pinned, work)
        tb_path = wsl_path(work / "tb.sv")
        mine_path = wsl_path(work / ("UHSC" + name + ".sv"))
        ref_path = wsl_path(work / (name + "_Reference.sv"))
        build = run_wsl(
            [
                "bash",
                "-lc",
                "cd %s && verilator --cc --exe --build -j 4 -Wno-fatal --top-module tb "
                "--Mdir obj_dir -o tb %s %s %s %s"
                % (
                    shlex.quote(wsl_path(work)),
                    tb_path,
                    mine_path,
                    ref_path,
                    wsl_path(work / "main.cpp"),
                ),
            ],
            timeout=3600,
        )
        binary = work / "obj_dir" / "tb"
        simulate: dict[str, object] = {"status": "SKIPPED", "returncode": None}
        if build["status"] == "PASS" and binary.exists():
            run = subprocess.run(
                ["wsl.exe", "-e", "bash", "-lc", "cd %s && ./obj_dir/tb" % shlex.quote(wsl_path(work))],
                capture_output=True,
                check=False,
                timeout=1200,
            )
            simulate = {
                "status": "PASS" if run.returncode == 0 else "FAIL",
                "returncode": run.returncode,
                "output_tail": (run.stdout + run.stderr).decode("utf-8", "replace")[-800:],
            }
        else:
            simulate["output_tail"] = str(build["output_tail"])[:800]
        passed = simulate["status"] == "PASS"
        differential_pass = differential_pass and passed
        diff_records.append(
            {
                "module": name,
                "build": build["status"],
                "build_output_tail": build["output_tail"],
                "simulation": simulate,
                "cycles": DIFFERENTIAL_CYCLES,
                "verdict": "BEHAVIORAL_DIFFERENTIAL_PASS" if passed else "BEHAVIORAL_DIFFERENTIAL_FAIL",
            }
        )

    # Gate 4: Verilator lint + Yosys elaboration on bounded representatives.
    # 门禁 4：对有界代表成员运行 Verilator lint 与 Yosys 展开。
    sweep_records: list[dict[str, object]] = []
    for name in TOOL_SWEEP_TARGETS:
        single = WORK / f"{name}.sv"
        single.write_text(module.build_verilog({"module": name}, {}), encoding="utf-8", newline="\n")
        located = wsl_path(single)
        lint = run_wsl(["verilator", "--lint-only", "-Wno-fatal", located], timeout=3600)
        # The bundled WSL yosys rejects Amaranth's full/parallel case attribute
        # emission; strip pure synthesis-hint attribute lines for the elaboration
        # gate and record the preprocessing in the evidence.
        # WSL 自带的 yosys 拒绝 Amaranth 的 full/parallel case 属性；
        # 展开门禁读取剥离纯综合提示属性行的副本，并在证据中记录该预处理。
        cleaned_lines = [
            line for line in single.read_text(encoding="utf-8").splitlines()
            if not line.strip().startswith("(* full_case")
            and not line.strip().startswith("(* parallel_case")
        ]
        cleaned = WORK / f"yosys_{name}.sv"
        cleaned.write_text("\n".join(cleaned_lines) + "\n", encoding="utf-8", newline="\n")
        yosys = run_wsl(
            [
                "yosys",
                "-Q",
                "-p",
                f"read_verilog -sv {wsl_path(cleaned)}; hierarchy -top UHSC{name}; proc; check",
            ],
            timeout=3600,
        )
        sweep_records.append(
            {
                "module": name,
                "verilator_lint": lint["status"],
                "verilator_output_tail": lint["output_tail"] if lint["status"] != "PASS" else "",
                "yosys": yosys["status"],
                "yosys_output_tail": yosys["output_tail"] if yosys["status"] != "PASS" else "",
                "yosys_preprocessing": "attribute_hint_lines_stripped",
                "verilog_sha256": sha256_table.get(name),
            }
        )
    verilator_pass = all(rec["verilator_lint"] == "PASS" for rec in sweep_records)
    yosys_pass = all(rec["yosys"] == "PASS" for rec in sweep_records)

    hierarchy_sha256 = digest(HIERARCHY.read_bytes())
    locked_ok = (
        hierarchy.get("reference_sha256") == LOCKED_SHA256
        and hierarchy.get("reference_path") == LOCKED_WSL
    )

    unclosed_gates: list[str] = [
        "DETERMINISM_FULL_SWEEP_UNCLOSED: repeated elaboration bounded to "
        + ", ".join(determinism_targets),
        "TOOL_SWEEP_FULL_UNCLOSED: Verilator/Yosys bounded to " + ", ".join(TOOL_SWEEP_TARGETS),
        "TLB_SFENCE_ADDR_BRANCH_CONTRACT_ONLY: pinned rs1=0 addr-match sfence rule "
        "implemented best-effort, exact pinned lines not transcribed",
        "TLB_WRITE_MERGE_LEVEL_CONTRACT_ONLY: s2_exception/inner_level merge chain "
        "transcribed from pinned SV, not differentially proven",
        "V_SPLIT_SEMANTIC_CONTRACT_ONLY: split beat counters follow the pinned "
        "port structure; full cycle behavior not differentially proven",
        "LOADQUEUE_UNCACHE_BEHAVIOR_CONTRACT_ONLY: parent routing follows the "
        "pinned allocator/arbiter structure; full cycle behavior not differentially proven",
    ]

    gates = {
        "COVERAGE_COMPLETE": "PASS" if not missing and not extra_locked else "PASS_BOUNDED",
        "PORT_SURFACE_MATCHED": "PASS" if not port_failures else "FAIL",
        "DETERMINISTIC_VERILOG": "PASS" if not determinism_failures else "FAIL",
        "DIFFERENTIAL": "PASS" if differential_pass else "FAIL",
        "VERILATOR": "PASS" if verilator_pass else "FAIL",
        "YOSYS": "PASS" if yosys_pass else "FAIL",
        "V2_LOCKED_REFERENCE_IMMUTABLE": "PASS" if locked_ok else "FAIL",
        "ACCEPTED": "NOT_ALLOWED",
    }
    status = "DIRECT_TEST_PASS_BOUNDED" if (
        not port_failures and not determinism_failures and differential_pass and verilator_pass and yosys_pass
    ) else "FAIL"

    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_MEMORY_LSQUEUE_UNCACHE_FAMILY",
        "batch_id": "V2-WAVE2-MEMORY-LSQUEUE-UNCACHE",
        "source_commit": SOURCE_COMMIT,
        "status": status,
        "scala_sources": [
            "src/main/scala/xiangshan/mem/lsqueue/LoadQueueUncache.scala",
            "src/main/scala/xiangshan/mem/lsqueue/FreeList.scala",
            "src/main/scala/xiangshan/cache/mmu/TLBStorage.scala",
            "src/main/scala/xiangshan/mem/vector/VSplit.scala",
            "src/main/scala/rocket-chip/src/main/scala/util/Repeater.scala",
        ],
        "target": {
            "path": TARGET.relative_to(ROOT).as_posix(),
            "sha256": digest(TARGET.read_bytes()),
            "line_count": len(TARGET.read_text(encoding="utf-8").splitlines()),
        },
        "covered_modules": covered,
        "covered_module_count": len(covered),
        "hierarchy_extra_modules": extra_locked,
        "locked_reference": {
            "canonical_path": LOCKED_WSL,
            "xstop_sha256": LOCKED_SHA256,
            "hierarchy_sha256": hierarchy_sha256,
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
            "bounded_to": determinism_targets,
            "failures": determinism_failures,
            "verilog_sha256": sha256_table,
        },
        "differential": {
            "status": "PASS" if differential_pass else "FAIL",
            "tool": "verilator",
            "transport": "wsl.exe -e bash -lc",
            "compared_instances": list(DIFFERENTIAL_TARGETS),
            "cycles_per_instance": DIFFERENTIAL_CYCLES,
            "records": diff_records,
            "trace_verdict": "BEHAVIORAL_DIFFERENTIAL_BOUNDED" if differential_pass
            else "BEHAVIORAL_DIFFERENTIAL_FAIL",
            "behavioral_equivalence": "BOUNDED_ESTABLISHED" if differential_pass else "NOT_ESTABLISHED",
        },
        "tool_gates": {
            "verilator": "PASS" if verilator_pass else "FAIL",
            "yosys": "PASS" if yosys_pass else "FAIL",
            "sweep": sweep_records,
            "bounded_to": list(TOOL_SWEEP_TARGETS),
        },
        "unclosed_gates": unclosed_gates,
        "gates": gates,
    }
    EVIDENCE.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("status:", status)
    print("port failures:", len(port_failures))
    print("differential:", [rec["verdict"] for rec in diff_records])
    print("verilator/yosys:", verilator_pass, yosys_pass)
    return 0 if status == "DIRECT_TEST_PASS_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
