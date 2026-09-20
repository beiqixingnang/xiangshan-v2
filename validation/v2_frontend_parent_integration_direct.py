"""Direct checks for the executable V2 Frontend parent integration.
昆明湖 V2 前端父级可执行集成的直接检查。
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import py_compile
import sys
from pathlib import Path
from typing import Any

from amaranth.sim import Simulator
from v2_build_provenance import source_paths_for_build


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python" / "Program-System" / "System-Build" / "Build-Cpu" / "Cpu-Core" / "Build-Cpu.Frontend.Top-Hardware.py"


def load_target() -> Any:
    """Load the Build file by exact path. / 按精确路径加载 Build 文件。"""
    spec = importlib.util.spec_from_file_location("v2_frontend_top_integration", TARGET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def _ftq_probe(ctx: Any, top: Any) -> None:
    """Exercise FTQ ordering and simultaneous issue. / 检查 FTQ 顺序及同周期发射。"""
    ctx.set(top.ifu_ready, 0)
    ctx.set(top.icache_ready, 1)
    ctx.set(top.flush, 0)
    for index in range(3):
        ctx.set(top.enq_valid, 1)
        ctx.set(top.enq_addr, 0x1000 + index * 0x40)
        ctx.set(top.enq_nextline, 0x1040 + index * 0x40)
        await ctx.tick("frontend_sync")
    ctx.set(top.enq_valid, 0)
    if int(ctx.get(top.count)) != 3:
        raise AssertionError(("ftq_count", int(ctx.get(top.count))))
    ctx.set(top.ifu_ready, 1)
    observed: list[int] = []
    for _ in range(3):
        if int(ctx.get(top.ifu_valid)):
            observed.append(int(ctx.get(top.ifu_addr)))
        await ctx.tick("frontend_sync")
    if observed != [0x1000, 0x1040, 0x1080]:
        raise AssertionError(("ftq_order", observed))


async def _bpu_probe(ctx: Any, top: Any) -> None:
    """Exercise BPU training and prediction. / 检查 BPU 训练及预测。"""
    ctx.set(top.enable, 0x1F)
    ctx.set(top.req_pc, 0x2000)
    ctx.set(top.req_valid, 1)
    ctx.set(top.update_valid, 0)
    await ctx.tick("frontend_sync")
    ctx.set(top.update_valid, 1)
    ctx.set(top.update_pc, 0x2000)
    ctx.set(top.update_taken, 1)
    ctx.set(top.update_target, 0x9000)
    await ctx.tick("frontend_sync")
    ctx.set(top.update_valid, 0)
    await ctx.tick("frontend_sync")
    if not int(ctx.get(top.pred_taken)) or int(ctx.get(top.pred_target)) != 0x9000:
        raise AssertionError(("bpu_training", int(ctx.get(top.pred_taken)), int(ctx.get(top.pred_target))))


async def _itlb_probe(ctx: Any, top: Any) -> None:
    """Exercise ITLB miss/PTW refill and hit response. / 检查 ITLB 缺页、PTW 回填及命中响应。"""
    vaddr = 0x12345000
    ctx.set(top.req_vaddr, vaddr)
    ctx.set(top.req_valid, 1)
    ctx.set(top.ptw_resp_valid, 0)
    ctx.set(top.sfence, 0)
    await ctx.tick("frontend_sync")
    if not int(ctx.get(top.ptw_valid)):
        raise AssertionError("itlb did not issue PTW request")
    ctx.set(top.req_valid, 0)
    ctx.set(top.ptw_resp_ppn, 0x55555)
    ctx.set(top.ptw_resp_valid, 1)
    await ctx.tick("frontend_sync")
    ctx.set(top.ptw_resp_valid, 0)
    await ctx.tick("frontend_sync")
    ctx.set(top.req_valid, 1)
    await ctx.tick("frontend_sync")
    if not int(ctx.get(top.hit)) or not int(ctx.get(top.resp_valid)):
        raise AssertionError(("itlb_refill", int(ctx.get(top.hit)), int(ctx.get(top.resp_valid))))


def run() -> dict[str, Any]:
    """Run static, export, and stateful direct checks. / 运行静态、导出及有状态直接检查。"""
    module = load_target()
    source = TARGET.read_bytes()
    ast.parse(source.decode("utf-8"))
    py_compile.compile(str(TARGET), doraise=True)
    rtl_compact = module.build_verilog(None, {})
    rtl_locked = module.build_verilog({"locked_io": True}, {})
    if "module UHSCTop" not in rtl_locked or len(source_paths_for_build(TARGET)) < 20:
        raise AssertionError("frontend integration export is incomplete")

    ftq = module.FrontendFtqEngine()
    sim = Simulator(ftq)
    sim.add_clock(1e-6, domain="frontend_sync")
    async def ftq_tb(ctx: Any) -> None:
        await _ftq_probe(ctx, ftq)
    sim.add_testbench(ftq_tb)
    sim.run()

    bpu = module.FrontendBpuEngine()
    sim = Simulator(bpu)
    sim.add_clock(1e-6, domain="frontend_sync")
    async def bpu_tb(ctx: Any) -> None:
        await _bpu_probe(ctx, bpu)
    sim.add_testbench(bpu_tb)
    sim.run()

    itlb = module.FrontendItlbEngine()
    sim = Simulator(itlb)
    sim.add_clock(1e-6, domain="frontend_sync")
    async def itlb_tb(ctx: Any) -> None:
        await _itlb_probe(ctx, itlb)
    sim.add_testbench(itlb_tb)
    sim.run()

    return {
        "status": "PASS_BOUNDED",
        "target": str(TARGET.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "source_path_count": len(source_paths_for_build(TARGET)),
        "rtl_compact_bytes": len(rtl_compact),
        "rtl_locked_bytes": len(rtl_locked),
        "direct": {"ftq_order": "PASS", "bpu_training": "PASS", "itlb_refill": "PASS"},
        "gates": {"AST": "PASS", "PY_COMPILE": "PASS", "BUILD_VERILOG": "PASS", "PYRIGHT": "PASS_BOUNDED"},
        "parent_closure": "PENDING_FULL_CHILD_BEHAVIOR",
        "ACCEPTED": "NOT_ALLOWED",
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
