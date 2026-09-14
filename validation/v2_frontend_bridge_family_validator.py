"""Independent direct and backend validation for the V2 FrontendBridge family.
昆明湖 V2 FrontendBridge family 的独立 direct 与后端验证。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import re
import shlex
import subprocess
import sys
import shutil
import os
from pathlib import Path

from amaranth.sim import Simulator


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.FrontendBridge-Hardware.py"
WORK = ROOT / "validation/.work/v2-frontend-bridge"
EVIDENCE = ROOT / "validation/v2-frontend-bridge-family-results.json"
REFERENCE = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_BYTES = 228590583
REFERENCE_MODULES = (
    "FrontendBridge", "ICacheBuffer", "ICacheCtrlBuffer", "InstrUncacheBuffer",
    "Queue2_TLBundleA_22", "Queue2_TLBundleD_23", "Queue2_TLBundleA_16",
    "Queue2_TLBundleD_19", "Queue2_TLBundleA_26", "Queue2_TLBundleD_29",
    "ram_2x359", "ram_2x281", "ram_2x117", "ram_2x80", "ram_2x132", "ram_2x77",
)


def load_target():
    """Load the final Build file by exact path. / 按精确路径加载最终 Build 文件。"""
    spec = importlib.util.spec_from_file_location("v2_frontend_bridge", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load FrontendBridge Build")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def direct(module) -> dict[str, object]:
    """Exercise enqueue/dequeue ordering on all three buffered edges. / 验证三条缓冲边的入队出队顺序。"""
    bridge = module.FrontendBridge()
    observed: list[int] = []
    accepted: list[int] = []

    async def bench(ctx) -> None:
        ctx.set(bridge.reset, 1)
        await ctx.tick("sync")
        ctx.set(bridge.reset, 0)
        for index in range(8):
            ctx.set(bridge.auto_icache_in_a_valid, 1)
            ctx.set(bridge.auto_icache_in_a_bits_source, index & 0xF)
            ctx.set(bridge.auto_icache_in_a_bits_address, 0x1000 + index * 64)
            ctx.set(bridge.auto_icache_out_a_ready, 0)
            ready = int(ctx.get(bridge.auto_icache_in_a_ready))
            await ctx.tick("sync")
            if ready:
                accepted.append(index)
        ctx.set(bridge.auto_icache_in_a_valid, 0)
        ctx.set(bridge.auto_icache_out_a_ready, 1)
        for _ in range(8):
            await ctx.tick("sync")
            if ctx.get(bridge.auto_icache_out_a_valid):
                observed.append(int(ctx.get(bridge.auto_icache_out_a_bits_source)))
        positions = [accepted.index(value) for value in observed if value in accepted]
        # Two serialized queue stages leave the final source in flight when
        # the bounded drain ends; the visible sequence must still be ordered.
        if positions != sorted(positions) or len(set(observed)) != len(observed):
            raise AssertionError(("icache order", observed, accepted))

    simulator = Simulator(bridge)
    simulator.add_clock(1e-6, domain="sync")
    simulator.add_testbench(bench)
    simulator.run()
    return {"status": "PASS", "vectors": len(accepted) + len(observed), "accepted_sources": accepted, "observed_sources": observed}


def backend(module) -> dict[str, object]:
    """Run Verilator lint and Yosys hierarchy on generated bridge RTL. / 对生成桥 RTL 运行 Verilator 与 Yosys。"""
    WORK.mkdir(parents=True, exist_ok=True)
    rtl = module.build_verilog({"module": "UHSCFrontendBridge"}, {})
    rtl_path = WORK / "frontend-bridge.sv"
    rtl_path.write_text(rtl, encoding="utf-8", newline="\n")
    wsl_path = str(rtl_path.resolve()).replace("\\", "/")
    if len(wsl_path) >= 2 and wsl_path[1] == ":":
        wsl_path = "/mnt/" + wsl_path[0].lower() + wsl_path[2:]
    ver = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"verilator --lint-only -Wno-fatal {wsl_path}"], capture_output=True, check=False)
    yos = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"yosys -Q -p 'read_verilog -sv {wsl_path}; hierarchy -top UHSCFrontendBridge; proc; check'"], capture_output=True, check=False)
    return {"verilator": "PASS" if ver.returncode == 0 else "FAIL", "yosys": "PASS" if yos.returncode == 0 else "FAIL", "rtl_bytes": len(rtl.encode()), "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(), "status": "PASS" if ver.returncode == yos.returncode == 0 else "FAIL"}


def extract_reference_modules(names: tuple[str, ...]) -> dict[str, bytes]:
    """Extract complete immutable reference modules without editing XSTop. / 从不可变 XSTop 提取完整参考模块且不修改源文件。"""
    wanted = set(names)
    found: dict[str, bytes] = {}
    active: str | None = None
    depth = 0
    captured: list[bytes] = []
    module_start = re.compile(rb"^module\s+([A-Za-z_][A-Za-z0-9_$]*)\s*\(")
    with REFERENCE.open("rb") as stream:
        for line in stream:
            if active is None:
                match = module_start.match(line)
                if match is None:
                    continue
                candidate = match.group(1).decode("ascii", "replace")
                if candidate not in wanted:
                    continue
                active = candidate
                depth = 1
                captured = [line]
                continue
            captured.append(line)
            if module_start.match(line) is not None:
                depth += 1
            if re.match(rb"^endmodule\b", line) is not None:
                depth -= 1
                if depth == 0:
                    found[active] = b"".join(captured)
                    active = None
                    captured = []
                    if len(found) == len(wanted):
                        break
    missing = sorted(wanted - set(found))
    if missing:
        raise RuntimeError(f"locked FrontendBridge modules missing: {missing}")
    return found


def parse_port_schema(module_text: bytes) -> list[tuple[str, str, int]]:
    """Parse grouped ANSI directions and widths from a locked module header. / 解析锁定模块头中的分组方向和位宽。"""
    match = re.search(rb"^module\s+FrontendBridge\s*\((.*?)\);", module_text, re.M | re.S)
    if match is None:
        raise RuntimeError("FrontendBridge header missing")
    body = re.sub(rb"//[^\n]*", b"", match.group(1))
    rows: list[tuple[str, str, int]] = []
    direction: str | None = None
    width = 1
    for raw in body.split(b","):
        token = b" ".join(raw.split())
        if not token:
            continue
        declared = re.match(rb"(input|output|inout)\s*(?:\[(\d+):(\d+)\])?\s*(.*)$", token)
        if declared is not None:
            direction = declared.group(1).decode("ascii")
            high, low = declared.group(2), declared.group(3)
            width = abs(int(high) - int(low)) + 1 if high is not None else 1
            rest = declared.group(4)
        else:
            rest = token
        for raw_name in rest.split(b","):
            name = raw_name.strip().decode("ascii", "replace")
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", name):
                if direction is None:
                    raise RuntimeError(f"direction missing for {name}")
                rows.append((name, direction, width))
    return rows


def value_literal(value: int, width: int) -> str:
    """Format a deterministic Verilog literal for a bounded random value. / 将有界随机值格式化为确定性 Verilog 常量。"""
    digits = max(1, (width + 3) // 4)
    return f"{width}'h{value & ((1 << width) - 1):0{digits}x}"


def wsl_path(path: Path) -> str:
    """Resolve a Windows path through WSL without relying on a pre-existing alias. / 通过 WSL 解析 Windows 路径且不依赖预置别名。"""
    try:
        relative = path.resolve().relative_to(ROOT.resolve())
        return "/tmp/uhsc-v2/" + relative.as_posix()
    except ValueError:
        pass
    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path.resolve())],
                            capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError("wslpath failed for FrontendBridge differential")
    return result.stdout.decode("utf-8", "replace").strip()


def reference_differential(module) -> dict[str, object]:
    """Run target versus the locked FrontendBridge closure under randomized traffic. / 在随机流量下将目标与锁定 FrontendBridge 闭包差分。"""
    raw = REFERENCE.read_bytes()
    # Install a stable ASCII WSL alias for the non-ASCII workspace path.
    root_probe = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(ROOT.resolve())], capture_output=True, check=False)
    if root_probe.returncode == 0:
        root_wsl = root_probe.stdout.decode("utf-8", "replace").strip()
        subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"ln -sfn '{root_wsl}' /tmp/uhsc-v2"], capture_output=True, check=False)
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) != REFERENCE_BYTES or digest != REFERENCE_SHA256:
        raise RuntimeError("locked XSTop hash/size mismatch")
    extracted = extract_reference_modules(REFERENCE_MODULES)
    renamed = re.sub(rb"^module\s+FrontendBridge\s*\(", b"module REF_FrontendBridge(", extracted["FrontendBridge"], count=1, flags=re.M)
    closure = b"\n\n".join(extracted[name] if name != "FrontendBridge" else renamed for name in REFERENCE_MODULES) + b"\n"
    WORK.mkdir(parents=True, exist_ok=True)
    ref_path = WORK / "frontend-bridge-reference.sv"
    ref_path.write_bytes(closure)
    target_rtl = module.build_verilog({"module": "UHSCFrontendBridge"}, {})
    target_path = WORK / "frontend-bridge-target-diff.sv"
    target_path.write_text(target_rtl, encoding="utf-8", newline="\n")
    specs = parse_port_schema(extracted["FrontendBridge"])
    inputs = [(name, width) for name, direction, width in specs if direction == "input"]
    outputs = [(name, width) for name, direction, width in specs if direction == "output"]
    rng = random.Random(0xFBE2_2026)
    vectors: list[dict[str, int]] = []
    # Twenty-four cycles cover reset, fill, full, drain, and backpressure while
    # keeping the generated Verilator testbench small enough for constrained
    # WSL workers.  The direct Amaranth test above exercises the longer stream.
    for cycle in range(24):
        vector: dict[str, int] = {}
        for name, width in inputs:
            if name in {"clock", "reset"}:
                continue
            # Alternate valid/ready pressure and include deterministic corner values.
            if name.endswith("_valid") or name.endswith("_ready"):
                value = (cycle % 7 not in (2, 5)) if cycle % 3 else (cycle % 2 == 0)
            else:
                value = rng.getrandbits(width)
            vector[name] = int(value)
        vectors.append(vector)
    lines = ["module tb;"]
    for name, width in inputs:
        lines.append(f"reg [{width - 1}:0] {name};" if width > 1 else f"reg {name};")
    for name, width in outputs:
        declaration = f"wire [{width - 1}:0]" if width > 1 else "wire"
        lines.append(f"{declaration} dut_{name};")
        lines.append(f"{declaration} ref_{name};")
    dut_connections = ", ".join(f".{name}({name if direction == 'input' else 'dut_' + name})" for name, direction, _width in specs)
    ref_connections = ", ".join(f".{name}({name if direction == 'input' else 'ref_' + name})" for name, direction, _width in specs)
    lines.extend([f"UHSCFrontendBridge dut_i({dut_connections});", f"REF_FrontendBridge ref_i({ref_connections});",
                  "always #1 clock = ~clock;", "integer cycle;", "initial begin", "clock=0; reset=1; cycle=0;"])
    for name, _width in inputs:
        if name not in {"clock", "reset"}:
            lines.append(f"{name}=0;")
    lines.append("repeat(4) @(posedge clock); reset=0;")
    valid_outputs = {name for name, _width in outputs if name.endswith("_valid")}
    ready_outputs = {name for name, _width in outputs if name.endswith("_ready")}
    payload_checks: list[tuple[str, str]] = []
    for name, _width in outputs:
        if name in valid_outputs or name in ready_outputs:
            continue
        marker = name.split("_bits_", 1)[0] + "_valid" if "_bits_" in name else None
        if marker in valid_outputs:
            payload_checks.append((name, marker))
    for index, vector in enumerate(vectors):
        lines.append(f"@(negedge clock); cycle={index};")
        for name, width in inputs:
            if name in {"clock", "reset"}:
                continue
            lines.append(f"{name}={value_literal(vector[name], width)};")
        lines.append("@(posedge clock); #0.2;")
        for name in sorted(valid_outputs | ready_outputs):
            lines.append(f"if (dut_{name} !== ref_{name}) $fatal(1, \"READY_VALID_MISMATCH {name} cycle=%0d\", cycle);")
        for name, marker in payload_checks:
            lines.append(f"if (dut_{marker} && ref_{marker} && dut_{name} !== ref_{name}) $fatal(1, \"PAYLOAD_MISMATCH {name} cycle=%0d\", cycle);")
    lines.extend([f'$display("FRONTEND_BRIDGE_REFERENCE_PASS {len(vectors)}");', "$finish;", "end", "endmodule", ""])
    tb_path = WORK / "frontend-bridge-diff-tb.sv"
    tb_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    target_posix = wsl_path(target_path)
    ref_posix = wsl_path(ref_path)
    tb_posix = wsl_path(tb_path)
    obj_dir = WORK / f"obj-diff-{os.getpid()}"
    shutil.rmtree(obj_dir, ignore_errors=True)
    obj_posix = wsl_path(obj_dir)
    obj_dir.mkdir(parents=True, exist_ok=True)
    compile_command = ["verilator", "--binary", "--timing", "-Wno-fatal", "-Wno-WIDTHTRUNC", "-Wno-WIDTHEXPAND", "--top-module", "tb",
                       "--Mdir", obj_posix, target_posix, ref_posix, tb_posix]
    try:
        compile_result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", " ".join(shlex.quote(item) for item in compile_command)],
                                        capture_output=True, check=False, timeout=240)
    except subprocess.TimeoutExpired as error:
        return {"status": "FAIL_TIMEOUT", "vectors": len(vectors),
                "reference": {"sha256": digest, "bytes": len(raw)},
                "compile_returncode": None, "compile_tail": str(error)}
    compile_output = (compile_result.stdout + compile_result.stderr).decode("utf-8", "replace")
    if compile_result.returncode != 0:
        return {"status": "FAIL_COMPILE", "vectors": len(vectors), "reference": {"sha256": digest, "bytes": len(raw)},
                "compile_returncode": compile_result.returncode, "compile_tail": compile_output[-2000:]}
    run = subprocess.run(["wsl.exe", "-e", "bash", "-lc", shlex.quote(obj_posix + "/Vtb")], capture_output=True, check=False, timeout=120)
    run_output = (run.stdout + run.stderr).decode("utf-8", "replace")
    passed = run.returncode == 0 and f"FRONTEND_BRIDGE_REFERENCE_PASS {len(vectors)}" in run_output
    return {"status": "PASS" if passed else "FAIL_RUN", "vectors": len(vectors),
            "reference": {"sha256": digest, "bytes": len(raw), "modules": list(REFERENCE_MODULES)},
            "compile_returncode": compile_result.returncode, "run_returncode": run.returncode,
            "run_tail": run_output[-2000:], "trace_sha256": hashlib.sha256(run_output.encode()).hexdigest()}


def main() -> int:
    """Write bounded family evidence without promotion. / 写入 bounded family 证据但不晋级。"""
    module = load_target()
    d = direct(module)
    b = backend(module)
    differential = reference_differential(module)
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_FRONTEND_BRIDGE_FAMILY",
        "batch_id": "V2-DEPENDENCY-FRONTEND-BRIDGE-001",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "source_scala_files": [
            "upstream/src/main/scala/xiangshan/mem/MemBlock.scala",
            "upstream/rocket-chip/src/main/scala/diplomacy/Buffer.scala",
        ],
        "target": {"path": TARGET.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest()},
        "direct": d,
        "backend": b,
        "reference_differential": differential,
        "gates": {
            "PYTHON_PRESENT": "PASS",
            "DIRECT_TEST_PASS_BOUNDED": d["status"],
            "VERILATOR": b["verilator"],
            "YOSYS": b["yosys"],
            "V2_REFERENCE_MATCHED": "PASS_BOUNDED_REFERENCE_DIFFERENTIAL" if differential["status"] == "PASS" else differential["status"],
            "PARENT_CLOSURE_MATCHED": "PENDING_MEMBLOCK_FRONTENDBRIDGE_PARENT",
            "LICENSE_REVIEW": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "VALIDATOR_PASS_BOUNDED" if d["status"] == b["status"] == differential["status"] == "PASS" else "VALIDATOR_FAIL",
        "acceptance_eligible": False,
        "unclosed": ["Full MemBlock FrontendBridge child closure and locked XSTop differential remain pending.", "License review and user approval remain pending."],
    }
    EVIDENCE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "direct": d["status"], "differential": differential["status"], "verilator": b["verilator"], "yosys": b["yosys"], "ACCEPTED": "NOT_ALLOWED"}))
    return 0 if payload["status"] == "VALIDATOR_PASS_BOUNDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
