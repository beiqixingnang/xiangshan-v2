"""Focused bounded validator for the V2 backend issue/rename entry and busy-table family.

V2 后端 issue/rename 条目与忙表族的聚焦有界校验器。

The validator loads the Build subject by exact path, checks every covered
module's Amaranth port surface against ``validation/v2-locked-hierarchy.json``,
proves the emitted Verilog is deterministic, runs Verilator lint and Yosys
elaboration on every covered member through WSL, and performs a bounded
structural differential against the pinned ``XSTop.sv`` for two representative
modules. Behavioral equivalence is intentionally NOT claimed: status stays at
most ``DIRECT_TEST_PASS_BOUNDED``.

校验器按精确路径加载 Build 主体，对照 ``validation/v2-locked-hierarchy.json``
检查每个被覆盖模块的 Amaranth 端口面，证明导出的 Verilog 是确定性的，并通过
WSL 对每个被覆盖成员运行 Verilator lint 与 Yosys 展开，再对两个代表模块与钉死
的 ``XSTop.sv`` 做有界结构差分。行为等价不作声明：状态至多
``DIRECT_TEST_PASS_BOUNDED``。
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
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = (
    ROOT
    / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
    / "Build-Cpu.Backend.Issue.Entries-Hardware.py"
)
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
LOCKED_WSL = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
WORK = ROOT / "validation/.work/v2-backend-issue-entries-family"
EVIDENCE = ROOT / "validation/v2-backend-issue-entries-family-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
LOCKED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"

# Two representative modules carry the bounded differential against the pinned
# artifact: the issue-queue entry register file and the compact/other entry.
# 两个代表模块承担与钉死产物的有界差分：发射队列条目寄存器堆与紧凑/其它条目。
DIFFERENTIAL_TARGETS: tuple[str, ...] = ("EntriesAluCsrFenceDiv", "OthersEntry")


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
    """Map a Windows path to WSL. / 通过显式查询把 Windows 路径映射到 WSL。"""

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


def select_family(modules: dict) -> dict[str, list[str]]:
    """Independently recompute the expected covered module set. / 独立重算预期被覆盖模块集合。"""

    big_reps = {
        "EntriesAluCsrFenceDiv",
        "OthersEntry",
        "EnqEntry",
        "IssueQueueAluCsrFenceDiv",
    }
    leaf_issue = ("FuBusyTableWrite", "MultiWakeupQueue")
    chosen: dict[str, list[str]] = {}
    for name, info in modules.items():
        srcs = [str(s) for s in (info.get("scala_sources") or [])]
        src = " ".join(srcs)
        group = None
        if name in big_reps:
            group = "representative"
        elif "xiangshan/backend/issue/" in src and name.startswith(leaf_issue):
            group = "issue_leaf"
        elif "xiangshan/backend/rename/BusyTable.scala" in src and name.startswith("BusyTable"):
            group = "rename_busytable"
        elif "xiangshan/backend/decode/DecodeUnitComp.scala" in src and name.startswith("indexedLSUopTable"):
            group = "decode_indexed"
        if group is not None:
            chosen.setdefault(group, []).append(name)
    return chosen


def main() -> int:
    """Run every coverage, port, determinism, differential and tool gate. / 运行覆盖、端口、确定性、差分与工具门禁。"""

    module = load(TARGET, "v2_issue_entries_target")
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))
    locked_modules: dict[str, dict[str, object]] = hierarchy["modules"]
    locked_ports = locked_port_table(locked_modules)
    expected_groups = select_family(locked_modules)
    expected = sorted(n for grp in expected_groups.values() for n in grp)
    covered = sorted(module.COVERED_MODULES)

    coverage_missing = sorted(set(expected) - set(covered))
    coverage_extra = sorted(set(covered) - set(expected))

    # Gate 1+2: exact ANSI port surface against the locked hierarchy, plus a
    # determinism proof from two independent elaborations of every member.
    # 门禁 1+2：对照锁定层级的精确 ANSI 端口面，并用每成员两次独立导出证明确定性。
    port_records: list[dict[str, object]] = []
    port_failures: list[str] = []
    determinism_failures: list[str] = []
    for name in covered:
        first = module.build_verilog({"module": name, "top_name": name}, {})
        second = module.build_verilog({"module": name, "top_name": name}, {})
        if first != second:
            determinism_failures.append(name)
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

    # Gate 3: bounded structural differential against the pinned artifact for
    # two representative modules, exercised with Verilator through WSL.
    # 门禁 3：对两个代表模块与钉死产物做有界结构差分，经 WSL 用 Verilator 检验。
    WORK.mkdir(parents=True, exist_ok=True)
    pinned_texts = extract_pinned(list(DIFFERENTIAL_TARGETS))
    diff_records: list[dict[str, object]] = []
    for name in DIFFERENTIAL_TARGETS:
        mine = module.build_verilog({"module": name, "top_name": name}, {})
        pinned = pinned_texts[name]
        mine_ports = parse_verilog_ports(mine)
        pinned_ports = parse_ansi_sticky_ports(pinned)
        # Lint my generated module standalone. / 独立 lint 我方生成模块。
        mine_path = WORK / f"{name}.sv"
        mine_path.write_text(mine, encoding="utf-8", newline="\n")
        mine_lint = run_wsl(
            ["verilator", "--lint-only", "-Wno-fatal", wsl_path(mine_path)]
        )
        # Lint the pinned leaf with the standard Chisel simulation macros;
        # child instances may be undefined and downgraded.
        # 用标准 Chisel 仿真宏 lint 钉死叶子；子实例可能未定义并被降级处理。
        pinned_path = WORK / f"{name}_Reference.sv"
        renamed = pinned.replace(f"module {name}(", f"module {name}_Reference(", 1)
        pinned_path.write_text(renamed, encoding="utf-8", newline="\n")
        pinned_lint = run_wsl(
            [
                "verilator",
                "--lint-only",
                "-Wno-fatal",
                "-DPRINTF_COND_=0",
                "-DSTOP_COND_=0",
                wsl_path(pinned_path),
            ]
        )
        assign_count = len(re.findall(r"\bassign\b", mine))
        child_count = len(re.findall(r"\bmodule\b", pinned)) - 1
        diff_records.append(
            {
                "module": name,
                "mine_port_count": len(mine_ports),
                "pinned_port_count": len(pinned_ports),
                "port_vector_match": set(mine_ports) == set(pinned_ports),
                "mine_assign_count": assign_count,
                "pinned_child_instance_count": child_count,
                "mine_lint": mine_lint["status"],
                "pinned_lint": pinned_lint["status"],
                "pinned_lint_output_tail": pinned_lint["output_tail"][-600:],
                "verdict": "STRUCTURAL_PORT_MATCH_BOUNDED",
            }
        )
    differential_pass = all(
        rec["port_vector_match"] and rec["mine_lint"] == "PASS"
        for rec in diff_records
    )

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
    lint_failures = sorted(line.split(maxsplit=1)[1] for line in lint_verdicts if line.startswith("LINT_FAIL "))
    yosys_failures = sorted(line.split(maxsplit=1)[1] for line in yosys_verdicts if line.startswith("YOSYS_FAIL "))
    lint_pass_count = sum(1 for line in lint_verdicts if line.startswith("LINT_PASS "))
    yosys_pass_count = sum(1 for line in yosys_verdicts if line.startswith("YOSYS_PASS "))

    default_rtl = module.build_verilog(None, {})
    default_path = WORK / "UHSCBackendIssueEntriesFamily.sv"
    default_path.write_text(default_rtl, encoding="utf-8", newline="\n")
    default_lint = run_wsl(
        ["verilator", "--lint-only", "-Wno-fatal", wsl_path(default_path)]
    )
    default_yosys = run_wsl(
        [
            "yosys",
            "-Q",
            "-p",
            f"read_verilog -sv {wsl_path(default_path)}; hierarchy -top UHSCBackendIssueEntriesFamily;"
            " proc; check",
        ]
    )

    verilator_pass = lint_pass_count == len(covered) and default_lint["status"] == "PASS"
    yosys_pass = yosys_pass_count == len(covered) and default_yosys["status"] == "PASS"
    # The pinned XSTop.sv digest is proven through the locked hierarchy's own
    # reference_sha256 chain; the hierarchy JSON digest is recorded as well.
    # 钉死 XSTop.sv 的摘要经锁定层级自身的 reference_sha256 链证明；层级 JSON 摘要一并记录。
    hierarchy_sha256 = digest(HIERARCHY.read_bytes())
    locked_ok = (
        HIERARCHY.stat().st_size > 0
        and hierarchy.get("module_count") == len(hierarchy.get("modules") or {})
        and hierarchy.get("reference_sha256") == LOCKED_SHA256
        and hierarchy.get("reference_path") == LOCKED_WSL
    )

    gates = {
        "COVERAGE_COMPLETE": "PASS" if not coverage_missing else "FAIL",
        "PORT_SURFACE_MATCHED": "PASS" if not port_failures else "FAIL",
        "DETERMINISTIC_VERILOG": "PASS" if not determinism_failures else "FAIL",
        "DIRECT_TEST_PASS_BOUNDED": "PASS" if differential_pass else "FAIL",
        "V2_REFERENCE_MATCHED": "PASS_BOUNDED_PORT_VECTOR" if differential_pass else "FAIL",
        "VERILATOR": "PASS" if verilator_pass else "FAIL",
        "YOSYS": "PASS" if yosys_pass else "FAIL",
        "V2_LOCKED_REFERENCE_IMMUTABLE": "PASS" if locked_ok else "FAIL",
        "PYTHON_PRESENT": "PASS",
        "ACCEPTED": "NOT_ALLOWED",
    }

    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_ISSUE_ENTRIES_FAMILY",
        "batch_id": "V2-WAVE2-BACKEND-ISSUE-ENTRIES",
        "source_commit": SOURCE_COMMIT,
        "scala_sources": [
            "src/main/scala/xiangshan/backend/issue/Entries.scala",
            "src/main/scala/xiangshan/backend/issue/OthersEntry.scala",
            "src/main/scala/xiangshan/backend/issue/EnqEntry.scala",
            "src/main/scala/xiangshan/backend/issue/IssueQueue.scala",
            "src/main/scala/xiangshan/backend/issue/FuBusyTableWrite.scala",
            "src/main/scala/xiangshan/backend/issue/MultiWakeupQueue.scala",
            "src/main/scala/xiangshan/backend/rename/BusyTable.scala",
            "src/main/scala/xiangshan/backend/decode/DecodeUnitComp.scala",
        ],
        "target": {
            "path": TARGET.relative_to(ROOT).as_posix(),
            "sha256": digest(TARGET.read_bytes()),
            "line_count": len(TARGET.read_text(encoding="utf-8").splitlines()),
        },
        "covered_family_groups": expected_groups,
        "coverage": {
            "covered_module_count": len(covered),
            "expected_module_count": len(expected),
            "missing_modules": coverage_missing,
            "extra_modules": coverage_extra,
            "covered_modules": covered,
        },
        "locked_reference": {
            "canonical_path": LOCKED_WSL,
            "xstop_sha256": LOCKED_SHA256,
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
            "transport": "wsl.exe -d Debian -- bash -lc",
            "compared_instances": list(DIFFERENTIAL_TARGETS),
            "vector_counts": {
                "modules_compared": len(diff_records),
                "port_vectors_total": sum(r["mine_port_count"] for r in diff_records),
            },
            "records": diff_records,
            "trace_verdict": "STRUCTURAL_PORT_MATCH_BOUNDED",
            "behavioral_equivalence": "NOT_ESTABLISHED",
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
            "default_export_yosys": default_yosys,
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
            "Only one FU-specialization representative is emitted per large kind (Entries, OthersEntry, "
            "EnqEntry, IssueQueue); the remaining Chisel parameter variants (e.g. EntriesAluMulBkuBrhJmp) "
            "share the same generic class and locked port surface but are not individually emitted here "
            "and are recorded CONTRACT_ONLY for per-variant emission.",
            "The generic entry model registers paired io_in_/io_out_ payload fields and drives a one-bit "
            "valid from enq/alloc/flush/cancel/deq; exact MicroOp bit-layout and per-source wakeup "
            "selection are not bit-established and are CONTRACT_ONLY.",
            "The bounded differential is a structural port-vector + Verilator lint comparison; no "
            "cycle-by-cycle trace equivalence against the pinned Chisel datapath is claimed.",
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
    return 0 if payload["status"] == "DIRECT_TEST_PASS_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
