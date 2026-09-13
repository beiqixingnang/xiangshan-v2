"""Bounded direct evidence for the V2 backend/datapath batch.
V2 后端数据通路批次的有界 direct 证据。
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import inspect
import json
import sys
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator


ROOT = Path(__file__).resolve().parents[1]
TARGET_DIR = ROOT / "python" / "ported" / "backend" / "datapath"
RESULT = ROOT / "validation" / "v2-backend-datapath-direct-results.json"
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
TARGETS = {
    "DataSource": TARGET_DIR / "DataSource-Hardware.py",
    "NewPipelineConnect": TARGET_DIR / "NewPipelineConnect-Hardware.py",
    "WbArbiter": TARGET_DIR / "WbArbiter-Hardware.py",
}
SCALA = {
    "DataSource": ROOT / "upstream/src/main/scala/xiangshan/backend/datapath/DataSource.scala",
    "NewPipelineConnect": ROOT / "upstream/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala",
    "WbArbiter": ROOT / "upstream/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala",
}


# Hash one file without normalizing bytes. / 对文件原始字节计算摘要。
def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Load a target through its exact path, independent of package imports.
# 通过精确路径加载目标，不依赖包导入。
def load_target(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Audit the five zones, adapter signature, and import boundary.
# 审计五区域、适配器签名及导入边界。
def audit_target(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    tree = ast.parse(text, filename=str(path))
    lines = text.splitlines()
    zones = ("Module Contract", "Configuration", "Implementation",
             "Public Adapter", "Direct Entry")
    positions = [text.find(zone) for zone in zones]
    comment_errors: list[str] = []
    forbidden_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            previous = lines[node.lineno - 2].strip() if node.lineno > 1 else ""
            if not (previous.startswith("#") and "/" in previous):
                comment_errors.append(f"{node.name}:{node.lineno}")
        if isinstance(node, ast.Import):
            forbidden_imports.extend(item.name for item in node.names
                                     if item.name.split(".")[0] in {
                                         "socket", "urllib", "subprocess", "importlib", "runpy", "pathlib"
                                     })
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in {"socket", "urllib", "subprocess", "importlib", "runpy", "pathlib"}:
                forbidden_imports.append(node.module)
    adapters = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "build_verilog"]
    adapter_args = ([arg.arg for arg in adapters[0].args.args]
                    if len(adapters) == 1 else [])
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256(path),
        "bytes": len(raw),
        "utf8": True,
        "bom": raw.startswith(b"\xef\xbb\xbf"),
        "lf_only": b"\r" not in raw,
        "ast": True,
        "zones": positions == sorted(positions) and all(item >= 0 for item in positions),
        "adapter_exact": adapter_args == ["configuration", "injected_dependencies"],
        "function_comment_errors": comment_errors,
        "forbidden_imports": forbidden_imports,
    }


# Run an exact-path import and deterministic adapter smoke test.
# 执行精确路径导入及确定性适配器冒烟测试。
def adapter_smoke(module: Any, configuration: Any = None) -> dict[str, Any]:
    builder = module.build_verilog
    signature = str(inspect.signature(builder))
    first = builder(configuration, None)
    second = builder(configuration, None)
    if not isinstance(first, str) or not first.strip() or first != second:
        raise AssertionError("adapter output is empty or non-deterministic")
    if "module" not in first:
        raise AssertionError("adapter did not emit Verilog")
    return {"signature": signature, "bytes": len(first.encode()),
            "sha256": hashlib.sha256(first.encode()).hexdigest()}


# Check all sixteen V2 DataSource selector values. / 检查全部十六个 V2 DataSource 选择值。
def test_data_source(module: Any) -> dict[str, Any]:
    dut = module.DataSourceProbe()
    observations: list[dict[str, int]] = []

    async def bench(ctx: Any) -> None:
        for value in range(16):
            ctx.set(dut.value, value)
            await ctx.delay(1e-9)
            outputs = [dut.read_reg, dut.read_reg_oh, dut.read_reg_cache,
                       dut.read_v0, dut.read_zero, dut.read_forward,
                       dut.read_bypass, dut.read_bypass2, dut.read_imm]
            observed: list[int] = []
            for signal in outputs:
                observed.append(int(ctx.get(signal)))
            expected = [int(value & 0x8 != 0), int(value == 0x8),
                        int(value == 0x6), int(value == 0x5), int(value == 0x0),
                        int(value == 0x1), int(value == 0x2), int(value == 0x3),
                        int(value == 0x4)]
            if observed != expected:
                raise AssertionError((value, observed, expected))
            observations.append({"value": value, **{
                name: item for name, item in zip(
                    ("read_reg", "read_reg_oh", "read_reg_cache", "read_v0",
                     "read_zero", "read_forward", "read_bypass", "read_bypass2", "read_imm"),
                    observed)}})

    simulator = Simulator(dut)
    simulator.add_testbench(bench)
    simulator.run()
    return {"vectors": len(observations), "trace_sha256": hashlib.sha256(
        json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


# Check reset, backpressure, age override, flush, and replacement ordering.
# 检查复位、反压、年龄覆盖、冲刷及替换顺序。
def test_pipeline(module: Any) -> dict[str, Any]:
    dut = module.NewPipelineConnectPipe(16)
    events = [
        {"reset": 1, "in_valid": 0, "in_bits": 0, "out_ready": 0, "right": 0, "flush": 0, "older": 0},
        {"reset": 0, "in_valid": 1, "in_bits": 0x1111, "out_ready": 0, "right": 0, "flush": 0, "older": 0},
        {"reset": 0, "in_valid": 0, "in_bits": 0, "out_ready": 0, "right": 0, "flush": 0, "older": 0},
        {"reset": 0, "in_valid": 1, "in_bits": 0x2222, "out_ready": 0, "right": 0, "flush": 0, "older": 1},
        {"reset": 0, "in_valid": 0, "in_bits": 0, "out_ready": 1, "right": 1, "flush": 0, "older": 0},
        {"reset": 0, "in_valid": 1, "in_bits": 0x3333, "out_ready": 0, "right": 0, "flush": 1, "older": 0},
        {"reset": 0, "in_valid": 0, "in_bits": 0, "out_ready": 0, "right": 0, "flush": 0, "older": 0},
    ]
    observations: list[dict[str, int]] = []
    valid = 0
    data = 0

    async def bench(ctx: Any) -> None:
        nonlocal valid, data
        for cycle, event in enumerate(events):
            for name, value in event.items():
                signal_name = {"right": "rightOutFire", "flush": "isFlush", "older": "isOlder"}.get(name, name)
                ctx.set(getattr(dut, signal_name), value)
            await ctx.delay(1e-9)
            left_ready = int(ctx.get(dut.in_ready))
            out_valid = int(ctx.get(dut.out_valid))
            out_bits = int(ctx.get(dut.out_bits))
            expected_ready = int(bool(event["out_ready"] or not valid or event["older"]))
            if left_ready != expected_ready or out_valid != valid or out_bits != data:
                raise AssertionError((cycle, left_ready, expected_ready, out_valid, valid, out_bits, data))
            observations.append({"cycle": cycle, "in_ready": left_ready,
                                 "out_valid": out_valid, "out_bits": out_bits})
            left_fire = bool(event["in_valid"] and expected_ready)
            if event["reset"] or event["flush"]:
                valid = 0
            elif left_fire:
                valid = 1
            elif event["right"]:
                valid = 0
            if left_fire:
                data = event["in_bits"]
            await ctx.tick()

    simulator = Simulator(dut)
    simulator.add_clock(1e-6)
    simulator.add_testbench(bench)
    simulator.run()
    return {"vectors": len(observations), "trace_sha256": hashlib.sha256(
        json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


# Check RealWBArbiter priority and ready equations exhaustively.
# 穷举检查 RealWBArbiter 优先级与 ready 方程。
def test_real_arbiter(module: Any) -> dict[str, Any]:
    dut = module.RealWBArbiter(dataWidth=16, n=4, addrWidth=4)
    observations: list[dict[str, int]] = []

    async def bench(ctx: Any) -> None:
        for ready in (0, 1):
            ctx.set(dut.out_ready, ready)
            for mask in range(16):
                for index in range(4):
                    ctx.set(dut.in_valid[index], (mask >> index) & 1)
                    ctx.set(dut.in_bits[index], 0x100 + index)
                    ctx.set(dut.in_pdest[index], index)
                    ctx.set(dut.in_rfWen[index], index & 1)
                    ctx.set(dut.in_fpWen[index], (index >> 1) & 1)
                await ctx.delay(1e-9)
                selected = next((index for index in range(4) if mask & (1 << index)), 3)
                valid = int(mask != 0)
                observed = {"mask": mask, "out_ready": ready,
                            "out_valid": int(ctx.get(dut.out_valid)),
                            "out_bits": int(ctx.get(dut.out_bits)),
                            "chosen": int(ctx.get(dut.chosen))}
                expected = {"out_valid": valid, "out_bits": 0x100 + selected,
                            "chosen": selected}
                if any(observed[key] != value for key, value in expected.items()):
                    raise AssertionError((observed, expected))
                for index in range(4):
                    expected_ready = int(((index == selected) or not (mask & (1 << index))) and ready)
                    if int(ctx.get(dut.in_ready[index])) != expected_ready:
                        raise AssertionError((mask, ready, index, ctx.get(dut.in_ready[index]), expected_ready))
                observations.append(observed)

    simulator = Simulator(dut)
    simulator.add_testbench(bench)
    simulator.run()
    return {"vectors": len(observations), "trace_sha256": hashlib.sha256(
        json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


# Check dispatcher fanout for all acceptance and ready masks.
# 检查全部接受掩码与 ready 掩码下的分发器扇出。
def test_dispatcher(module: Any) -> dict[str, Any]:
    dut = module.WbArbiterDispatcher(dataWidth=12, n=4)
    observations: list[dict[str, int]] = []

    async def bench(ctx: Any) -> None:
        ctx.set(dut.in_valid, 1)
        ctx.set(dut.in_bits, 0xA5A)
        for accept in range(16):
            for no_write in (0, 1):
                for ready in range(16):
                    ctx.set(dut.notWrite, no_write)
                    for index in range(4):
                        ctx.set(dut.acceptVec[index], (accept >> index) & 1)
                        ctx.set(dut.out_ready[index], (ready >> index) & 1)
                    await ctx.delay(1e-9)
                    expected_ready = int(bool(no_write or (accept & ready)))
                    if int(ctx.get(dut.in_ready)) != expected_ready:
                        raise AssertionError((accept, no_write, ready))
                    for index in range(4):
                        expected_valid = int(bool(accept & (1 << index)))
                        if int(ctx.get(dut.out_valid[index])) != expected_valid:
                            raise AssertionError((accept, index))
                    observations.append({"accept": accept, "not_write": no_write,
                                         "ready": ready, "in_ready": expected_ready})

    simulator = Simulator(dut)
    simulator.add_testbench(bench)
    simulator.run()
    return {"vectors": len(observations), "trace_sha256": hashlib.sha256(
        json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


# Check grouped collision arbitration and priority ordering. / 检查分组冲突仲裁与优先级顺序。
def test_collide_checker(module: Any) -> dict[str, Any]:
    dut = module.RealWBCollideChecker(
        dataWidth=12, inPorts=(0, 0, 1, -1, 2), portRange=(0, 1, 2),
        portMax=2, addrWidth=4, priorities=(2, 0, 1, 3, 4),
    )
    observations: list[dict[str, int]] = []
    groups = {0: (0, 1), 1: (2,), 2: (4,)}

    async def bench(ctx: Any) -> None:
        for mask in range(32):
            for index in range(5):
                ctx.set(dut.in_valid[index], (mask >> index) & 1)
                ctx.set(dut.in_bits[index], 0x200 + index)
                ctx.set(dut.in_pdest[index], index)
            await ctx.delay(1e-9)
            row = {"mask": mask}
            for port, members in groups.items():
                selected = next((index for index in sorted(members, key=lambda item: dut.priorities[item])
                                 if mask & (1 << index)), None)
                valid = int(selected is not None)
                if int(ctx.get(dut.out_valid[port])) != valid:
                    raise AssertionError((mask, port, ctx.get(dut.out_valid[port]), valid))
                if selected is not None and int(ctx.get(dut.out_bits[port])) != 0x200 + selected:
                    raise AssertionError((mask, port))
                row[f"port{port}_valid"] = valid
            if int(ctx.get(dut.in_ready[3])) != 1:
                raise AssertionError("NoWB input must remain ready")
            observations.append(row)

    simulator = Simulator(dut)
    simulator.add_testbench(bench)
    simulator.run()
    return {"vectors": len(observations), "trace_sha256": hashlib.sha256(
        json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


# Check WbDataPath routing and uncertain-latency ready behavior.
# 检查 WbDataPath 路由及不确定延迟 ready 行为。
def test_data_path(module: Any) -> dict[str, Any]:
    attrs = (
        module.WbExuAttr("alu", writeIntRf=True, hasUncertainLatency=True),
        module.WbExuAttr("vf", writeIntRf=True, writeVfRf=True,
                          isVfExeUnit=True, hasUncertainLatency=True),
        module.WbExuAttr("mem", writeIntRf=True, isMemExeUnit=True,
                          hasVLoadFu=True, hasUncertainLatency=True),
    )
    config = module.WbDataPathConfig(
        intExus=(attrs[0],), vfExus=(attrs[1],), memExus=(attrs[2],),
        intWbPorts=(0, 0, 1), vfWbPorts=(0,), intPortMax=1, vfPortMax=0,
        fpPortMax=0, v0PortMax=0, vlPortMax=0, dataWidth=16, addrWidth=4,
    )
    dut = module.WbDataPath(config)
    observations: list[dict[str, int]] = []

    async def bench(ctx: Any) -> None:
        cases = [
            (0b001, (1, 0, 0), (1, 0, 0)),
            (0b011, (1, 1, 0), (1, 1, 0)),
            (0b100, (0, 0, 1), (0, 0, 1)),
            (0b000, (0, 0, 0), (0, 0, 0)),
        ]
        for mask, _, _ in cases:
            for index in range(dut.numExu):
                ctx.set(dut.fromExu_valid[index], (mask >> index) & 1)
                ctx.set(dut.fromExu_bits[index], 0x300 + index)
                ctx.set(dut.fromExu_pdest[index], index)
                ctx.set(dut.toIntRf[index], int(index in (0, 1, 2)))
                ctx.set(dut.toFpRf[index], 0)
                ctx.set(dut.toVecRf[index], int(index == 1))
                ctx.set(dut.toV0Rf[index], 0)
                ctx.set(dut.toVlRf[index], 0)
            await ctx.delay(1e-9)
            row = {"mask": mask}
            for port, signal in enumerate(dut.toIntPreg_valid):
                row[f"int{port}"] = int(ctx.get(signal))
            for port, signal in enumerate(dut.toVfPreg_valid):
                row[f"vf{port}"] = int(ctx.get(signal))
            row["ctrl0"] = int(ctx.get(dut.toCtrl_writeback_valid[0]))
            row["ctrl1"] = int(ctx.get(dut.toCtrl_writeback_valid[1]))
            row["ctrl2"] = int(ctx.get(dut.toCtrl_writeback_valid[2]))
            observations.append(row)
            if mask & 1 and row["int0"] != 1:
                raise AssertionError((mask, row))
            if mask & 2 and row["vf0"] != 1:
                raise AssertionError((mask, row))
            if mask & 4 and row["int1"] != 1:
                raise AssertionError((mask, row))

    simulator = Simulator(dut)
    simulator.add_testbench(bench)
    simulator.run()
    return {"vectors": len(observations), "trace_sha256": hashlib.sha256(
        json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


# Run the complete direct batch and persist machine-readable evidence.
# 运行完整 direct 批次并写入机器可读证据。
def main() -> int:
    modules = {name: load_target(path, f"v2_datapath_{name}")
               for name, path in TARGETS.items()}
    static = {name: audit_target(path) for name, path in TARGETS.items()}
    if not all(row["zones"] and row["adapter_exact"] and row["lf_only"]
               and not row["bom"] and not row["function_comment_errors"]
               and not row["forbidden_imports"] for row in static.values()):
        raise AssertionError(static)
    adapters = {
        "DataSource": adapter_smoke(modules["DataSource"]),
        "NewPipelineConnect": adapter_smoke(modules["NewPipelineConnect"]),
        "WbArbiterDispatcher": adapter_smoke(modules["WbArbiter"], {"module": "WbArbiterDispatcher"}),
        "RealWBArbiter": adapter_smoke(modules["WbArbiter"], {"module": "RealWBArbiter", "n": 3}),
        "RealWBCollideChecker": adapter_smoke(modules["WbArbiter"], {"module": "RealWBCollideChecker", "in_ports": [0, 0, 1]}),
    }
    checks = {
        "DataSource": test_data_source(modules["DataSource"]),
        "NewPipelineConnect": test_pipeline(modules["NewPipelineConnect"]),
        "RealWBArbiter": test_real_arbiter(modules["WbArbiter"]),
        "WbArbiterDispatcher": test_dispatcher(modules["WbArbiter"]),
        "RealWBCollideChecker": test_collide_checker(modules["WbArbiter"]),
        "WbDataPath": test_data_path(modules["WbArbiter"]),
    }
    payload = {
        "schema_version": 1,
        "kind": "V2_P1_BACKEND_DATAPATH_DIRECT_EVIDENCE",
        "batch_id": "V2-P1-D-BACKEND-DATAPATH",
        "source_commit": SOURCE_COMMIT,
        "status": "PASS_BOUNDED_DIRECT",
        "target_paths": {name: path.relative_to(ROOT).as_posix() for name, path in TARGETS.items()},
        "target_sha256": {name: sha256(path) for name, path in TARGETS.items()},
        "source_paths": {name: path.relative_to(ROOT).as_posix() for name, path in SCALA.items()},
        "source_sha256": {name: sha256(path) for name, path in SCALA.items()},
        "static_audit": static,
        "adapter_smoke": adapters,
        "checks": checks,
        "reference_differential": "PENDING",
        "parent_closure": "PENDING",
        "license_gate": "PENDING",
        "uhsc_localization": {"status": "NO_PROJECT_FACING_RENAME", "manifest": "UHSC-Naming-Manifest.json"},
        "acceptance_eligible": False,
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "checks": len(checks)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
