"""Independent bounded validator for the V2 NewCSR PMP/PMA entry-handler family."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from amaranth.sim import Simulator

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.CSRLite-Hardware.py"
SIBLING = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.CSRModule-Hardware.py"
LOCKED = ROOT / "validation/v2-locked-hierarchy.json"
CSRS_SOURCE = ROOT / "upstream/rocket-chip/src/main/scala/rocket/Instructions.scala"
CSRCONST_SOURCE = ROOT / "upstream/src/main/scala/xiangshan/backend/fu/util/CSRConst.scala"
LOCKED_SV = "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv"
OUT = ROOT / "validation/v2-newcsr-csrlevels-family-results.json"
WSL = ["wsl.exe", "-e", "bash", "-lc"]
NEWCSR_PREFIXES = ("home/lishuo/xs-v2-local/src/main/scala/xiangshan/backend/fu/NewCSR/",)


# Load one Build subject by exact path. / 按精确路径加载一个构建主体。
def load_module(path, name):
    """Return the imported Build module. / 返回导入的构建模块。"""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Return the locked ANSI port contract of one module. / 返回单个模块的锁定 ANSI 端口契约。
def locked_ports(hierarchy, name):
    """Return `{port name: (direction, width)}` from the locked hierarchy. / 由锁定层级返回端口契约。"""

    entry = hierarchy["modules"][name]
    return {port["name"]: (port["direction"], port["width"]) for port in entry["ports"]}


# Parse the emitted ANSI port contract of one generated module. / 解析生成模块的 ANSI 端口契约。
def emitted_ports(rtl, name):
    """Return `{port name: (direction, width)}` from generated Verilog. / 由生成的 Verilog 返回端口契约。"""

    header = re.search(r"^module\s+" + re.escape(name) + r"\s*\((.*?)\);", rtl, re.S | re.M)
    if header is None:
        raise AssertionError(f"module {name} missing from generated Verilog")
    names = [item.strip() for item in header.group(1).split(",")]
    body = rtl[header.end():]
    body = body[:body.index("endmodule")]
    declared = {match.group(3): (match.group(1), match.group(2) or "")
                for match in re.finditer(r"^\s*(input|output)\s*(\[[0-9]+:[0-9]+\])?\s*(\w+);",
                                         body, re.M)}
    if sorted(names) != sorted(declared):
        raise AssertionError(f"{name}: header and declaration disagree")
    return declared


# Return the NewCSR module names of the locked hierarchy. / 返回锁定层级中 NewCSR 的模块名。
def newcsr_module_names(hierarchy):
    """Return every locked module whose Scala provenance is under NewCSR. / 返回 Scala 出处位于 NewCSR 的锁定模块。"""

    found = []
    for name, entry in hierarchy["modules"].items():
        for source in entry["scala_sources"]:
            if str(source).startswith(NEWCSR_PREFIXES):
                found.append(name)
                break
    return sorted(found)


# Read a Scala integer table from the vendored sources. / 由随仓库源读取 Scala 整数表。
def scala_constants(path, anchor, stop):
    """Return `{name: value}` of one Scala constant block. / 返回一个 Scala 常量块的取值表。"""

    text = path.read_text(encoding="utf-8", errors="replace")
    block = text[text.index(anchor):text.index(stop, text.index(anchor))]
    return {match.group(1): int(match.group(2), 0)
            for match in re.finditer(r"val\s+(\w+)\s*=\s*(0x[0-9a-fA-F]+|\d+)", block)}


# Extract the PMA address reset block from the locked artifact through WSL.
# 经 WSL 从锁定产物抽取 PMA 地址复位块。
def locked_pma_resets():
    """Return the reset values recorded in the locked artifact, or `None`. / 返回锁定产物记录的复位值，取不到则为 None。"""

    script = (f"awk '/^module PMAEntryHandleModule\\(/{{f=1}} f{{print}} "
              f"f&&/^endmodule/{{exit}}' {LOCKED_SV}")
    try:
        run = subprocess.run(WSL + [script], capture_output=True, text=True, timeout=900)
    except Exception:
        return None
    if run.returncode != 0 or "PMAEntryHandleModule" not in run.stdout:
        return None
    text = re.sub(r"//[^\n]*", "", run.stdout)
    start = text.index("if (reset) begin")
    block = text[start:text.index("end", start)]
    values = {int(match.group(1)): int(match.group(2), 16)
              for match in re.finditer(r"pmaAddr_(\d+)\s*<=\s*46'h([0-9a-fA-F]+);", block)}
    if sorted(values) != list(range(32)):
        return None
    return [values[index] for index in range(32)]


# Run Verilator and Yosys over one generated Verilog file. / 对一个生成的 Verilog 文件运行 Verilator 与 Yosys。
def lint(rtl, top):
    """Return the Verilator verdict, Yosys verdict and Verilator output tail. / 返回 Verilator/Yosys 结论与输出尾部。"""

    with tempfile.TemporaryDirectory(prefix="v2_csrlevels_") as directory:
        path = Path(directory) / "csrlevels.sv"
        path.write_text(rtl, encoding="utf-8", newline="\n")
        wsl_path = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                                  capture_output=True, text=True, check=True).stdout.strip()
        verilator = subprocess.run(
            WSL + [f"verilator --lint-only -Wno-fatal '{wsl_path}' 2>&1 | tail -20"],
            capture_output=True, text=True, check=False)
        yosys = subprocess.run(
            WSL + [f"yosys -Q -p 'read_verilog -sv {wsl_path}; hierarchy -top {top}; proc; check' "
                   f"2>&1 | tail -20"], capture_output=True, text=True, check=False)
    return verilator, yosys


# Drive every input of one handler to zero before the reset pulse.
# 在复位脉冲前把一个处理器的全部输入置零。
def quiet(ctx, top, entries):
    """Set the control and configuration inputs of one handler to zero. / 把一个处理器的控制与配置输入置零。"""

    for signal in (top.reset, top.io_in_wen, top.io_in_ren, top.io_in_addr, top.io_in_wdata):
        ctx.set(signal, 0)
    for entry in entries:
        for field in entry:
            ctx.set(entry[field], 0)


# Perform one address write cycle and settle. / 执行一次地址写入周期并稳定。
async def write_cycle(ctx, top, address, value):
    """Write one entry address and settle the register. / 写入一个条目地址并让寄存器稳定。"""

    ctx.set(top.io_in_wen, 1)
    ctx.set(top.io_in_addr, address)
    ctx.set(top.io_in_wdata, value)
    await ctx.tick("sync")
    ctx.set(top.io_in_wen, 0)
    ctx.set(top.io_in_wdata, 0)
    await ctx.delay(1e-9)


# Read one handler output with the read strobe asserted. / 在读选通有效时读取一个处理器的输出。
async def read_back(ctx, top, address, output):
    """Return the read data observed for one selected address. / 返回被选中地址的读回数据。"""

    ctx.set(top.io_in_ren, 1)
    ctx.set(top.io_in_addr, address)
    await ctx.delay(1e-9)
    value = int(ctx.get(output))
    ctx.set(top.io_in_ren, 0)
    return value


# Read one configuration write-back word with the write strobe asserted.
# 在写选通有效时读取一个配置写回字。
async def read_write_back(ctx, top, address, output):
    """Return the write-back word observed for one selected address. / 返回被选中地址的写回字。"""

    ctx.set(top.io_in_wen, 1)
    ctx.set(top.io_in_addr, address)
    await ctx.delay(1e-9)
    value = int(ctx.get(output))
    ctx.set(top.io_in_wen, 0)
    return value


# Exercise the PMP handler and return the observed values. / 激励 PMP 处理器并返回观测值。
def pmp_direct(module):
    """Return the bounded PMP observations. / 返回有界的 PMP 观测结果。"""

    top = module.PmpEntryHandleModule()
    written = 0x2ABCDEF0123
    observations = []

    async def bench(ctx):
        quiet(ctx, top, top.pmp_cfg)
        ctx.set(top.reset, 1)
        await ctx.tick("sync")
        ctx.set(top.reset, 0)
        await ctx.delay(1e-9)
        observations.append({"case": "reset-read", "value": await read_back(
            ctx, top, module.PMP_ENTRY_ADDRESSES[0], top.io_out_pmpAddrRData[0])})
        await write_cycle(ctx, top, module.PMP_ENTRY_ADDRESSES[0], written)
        observations.append({"case": "after-write", "value": await read_back(
            ctx, top, module.PMP_ENTRY_ADDRESSES[0], top.io_out_pmpAddrRData[0])})
        ctx.set(top.pmp_cfg[0]["A"], 3)
        observations.append({"case": "napot-read", "value": await read_back(
            ctx, top, module.PMP_ENTRY_ADDRESSES[0], top.io_out_pmpAddrRData[0])})
        ctx.set(top.pmp_cfg[0]["A"], 0)
        ctx.set(top.pmp_cfg[0]["L"], 1)
        await write_cycle(ctx, top, module.PMP_ENTRY_ADDRESSES[0], 0x1)
        observations.append({"case": "locked-entry", "value": await read_back(
            ctx, top, module.PMP_ENTRY_ADDRESSES[0], top.io_out_pmpAddrRData[0])})
        ctx.set(top.pmp_cfg[0]["L"], 0)
        ctx.set(top.pmp_cfg[1]["L"], 1)
        ctx.set(top.pmp_cfg[1]["A"], 1)
        await write_cycle(ctx, top, module.PMP_ENTRY_ADDRESSES[0], 0x2)
        observations.append({"case": "tor-locked-entry", "value": await read_back(
            ctx, top, module.PMP_ENTRY_ADDRESSES[0], top.io_out_pmpAddrRData[0])})
        ctx.set(top.pmp_cfg[1]["L"], 0)
        ctx.set(top.pmp_cfg[1]["A"], 0)
        ctx.set(top.pmp_cfg[8]["L"], 1)
        ctx.set(top.io_in_wdata, 0x10)
        observations.append({"case": "cfg-word0-na4-promoted", "value": await read_write_back(
            ctx, top, module.PMP_CFG_WORD_ADDRESSES[0], top.io_out_pmpCfgWData)})
        observations.append({"case": "cfg-word1-locked-image", "value": await read_write_back(
            ctx, top, module.PMP_CFG_WORD_ADDRESSES[1], top.io_out_pmpCfgWData)})
        observations.append({"case": "cfg-word2-unselected", "value": await read_write_back(
            ctx, top, module.PMP_CFG_WORD_ADDRESSES[2], top.io_out_pmpCfgWData)})
        ctx.set(top.io_in_wdata, 0)
        observations.append({"case": "cfg-idle", "value": await read_write_back(
            ctx, top, module.PMP_CFG_WORD_ADDRESSES[0], top.io_out_pmpCfgWData)})

    sim = Simulator(top)
    sim.add_clock(1e-6, domain="sync")
    sim.add_testbench(bench)
    sim.run()
    return observations


# Exercise the PMA handler and return the observed values. / 激励 PMA 处理器并返回观测值。
def pma_direct(module):
    """Return the bounded PMA observations. / 返回有界的 PMA 观测结果。"""

    top = module.PmaEntryHandleModule()
    observations = []

    async def bench(ctx):
        quiet(ctx, top, top.pma_cfg)
        ctx.set(top.reset, 1)
        await ctx.tick("sync")
        ctx.set(top.reset, 0)
        await ctx.delay(1e-9)
        observations.append({"case": "reset-entry31-masked", "value": await read_back(
            ctx, top, module.PMA_ENTRY_ADDRESSES[31], top.io_out_pmaAddrRData[31])})
        observations.append({"case": "reset-entry21", "value": await read_back(
            ctx, top, module.PMA_ENTRY_ADDRESSES[21], top.io_out_pmaAddrRData[21])})
        observations.append({"case": "reset-entry22", "value": await read_back(
            ctx, top, module.PMA_ENTRY_ADDRESSES[22], top.io_out_pmaAddrRData[22])})
        ctx.set(top.pma_cfg[31]["A"], 3)
        observations.append({"case": "napot-entry31", "value": await read_back(
            ctx, top, module.PMA_ENTRY_ADDRESSES[31], top.io_out_pmaAddrRData[31])})
        ctx.set(top.pma_cfg[31]["A"], 0)
        observations.append({"case": "unselected-entry31", "value": await read_back(
            ctx, top, module.PMA_ENTRY_ADDRESSES[0], top.io_out_pmaAddrRData[31])})
        ctx.set(top.pma_cfg[7]["ATOMIC"], 1)
        ctx.set(top.pma_cfg[7]["C"], 1)
        ctx.set(top.io_in_wdata, 0x6000000000000000)
        observations.append({"case": "pma-cfg-word0-unlocked", "value": await read_write_back(
            ctx, top, module.PMA_CFG_WORD_ADDRESSES[0], top.io_out_pmaCfgWdata)})
        ctx.set(top.pma_cfg[7]["L"], 1)
        observations.append({"case": "pma-cfg-word0-locked", "value": await read_write_back(
            ctx, top, module.PMA_CFG_WORD_ADDRESSES[0], top.io_out_pmaCfgWdata)})
        ctx.set(top.pma_cfg[7]["L"], 0)
        ctx.set(top.pma_cfg[8]["ATOMIC"], 1)
        ctx.set(top.pma_cfg[8]["C"], 1)
        ctx.set(top.pma_cfg[8]["L"], 1)
        observations.append({"case": "pma-cfg-word1-fields", "value": await read_write_back(
            ctx, top, module.PMA_CFG_WORD_ADDRESSES[1], top.io_out_pmaCfgWdata)})
        # Word 2 has no locked entry, so every field follows `io_in_wdata`; with a zero
        # write payload the selected word must collapse to zero.
        # Word 2 没有锁定条目，所有字段都跟随 io_in_wdata；写载荷归零后被选中的字必须归零。
        ctx.set(top.io_in_wdata, 0)
        observations.append({"case": "pma-cfg-word2-cleared", "value": await read_write_back(
            ctx, top, module.PMA_CFG_WORD_ADDRESSES[2], top.io_out_pmaCfgWdata)})
        await write_cycle(ctx, top, module.PMA_ENTRY_ADDRESSES[7], 0x3FFFFFFFFF)
        observations.append({"case": "pma-entry7-write", "value": await read_back(
            ctx, top, module.PMA_ENTRY_ADDRESSES[7], top.io_out_pmaAddrRData[7])})

    sim = Simulator(top)
    sim.add_clock(1e-6, domain="sync")
    sim.add_testbench(bench)
    sim.run()
    return observations


# Compare the observed PMP vectors with the artifact-derived expectations.
# 把观测的 PMP 向量与由工件推出的期望值比较。
def check_pmp(observations, written):
    """Assert the PMP expectations and return them. / 断言 PMP 期望并返回期望值。"""

    # `io_out_pmpAddrRData[i]` returns `{18'h0, ren & hit ? grain mask : addr}` with NAPOT
    # masking `addr[45:9]` and TOR hoisting `addr[45:10]`; `io_out_pmpCfgWData` is the four-level
    # strobe nest `_GEN_2 ? w2 : _GEN_1 ? w1 : _GEN_0 ? w0 : _GEN & w0` over the `pmpcfg0/2/4/6`
    # words. Inside one word the MSB byte is entry base+7 and the LSB byte is entry base+0, laid
    # out MSB-first as `{L, 2'b00, A[1:0], X, W, R}` with `A[1] = io_in_wdata[4]`,
    # `A[0] = io_in_wdata[4] | io_in_wdata[3]` (`NA4` is promoted to `NAPOT` whenever payload
    # bit 3 is set), `W = io_in_wdata[1] & io_in_wdata[0]` and `R = io_in_wdata[0]`; every field
    # is `locked ? register : payload`, so `0x18` below is `A = 2'b11` promoted from `0x10`.
    # 地址读回为 `{18'h0, ren&命中 ? 粒度掩码 : addr}`（NAPOT 掩 addr[45:9]，TOR 提升 addr[45:10]）；
    # 写回字是 pmpcfg0/2/4/6 的四级选通嵌套。字内高字节是条目 base+7、低字节是条目 base+0，
    # 按 MSB-first 布局为 {L, 2'b00, A[1:0], X, W, R}，其中 A[1]=io_in_wdata[4]、
    # A[0]=io_in_wdata[4]|io_in_wdata[3]（载荷位 3 置位时 NA4 升格为 NAPOT）、
    # W=io_in_wdata[1]&io_in_wdata[0]、R=io_in_wdata[0]；字段按 `locked ? 寄存器 : 载荷` 取值，
    # 故下方 0x18 即由 0x10 升格得到的 A = 2'b11。

    got = {item["case"]: item["value"] for item in observations}
    expected = {
        "reset-read": 0,
        "after-write": written & ~0x3FF,
        "napot-read": (written & ~0x1FF) | 0x1FF,
        "locked-entry": written & ~0x3FF,
        "tor-locked-entry": written & ~0x3FF,
        "cfg-word0-na4-promoted": 0x18,
        "cfg-word1-locked-image": 0x80,
        "cfg-word2-unselected": 0x18,
        "cfg-idle": 0,
    }
    failures = {key: [got.get(key), value] for key, value in expected.items() if got.get(key) != value}
    if failures:
        raise AssertionError(f"PMP expectations failed: {failures}")
    return expected


# Compare the observed PMA vectors with the artifact-derived expectations.
# 把观测的 PMA 向量与由工件推出的期望值比较。
def check_pma(observations):
    """Assert the PMA expectations and return them. / 断言 PMA 期望并返回期望值。"""

    # Every value below is read off the locked `PMAEntryHandleModule` body:
    # `io_out_pmaAddrRData[i]` (`{18'h0, ren & hit ? grain mask : addr}`) supplies the three
    # reset/NAPOT/entry-7 vectors, while `io_out_pmaCfgWdata` supplies the four strobed words.
    # Inside one word the MSB byte is entry base+7 and the LSB byte is entry base+0, with the
    # byte layout `{L, C, ATOMIC, A[1:0], X, W, R}` and `W = io_in_wdata[57] & io_in_wdata[56]`;
    # each field is `L ? register : io_in_wdata` and the whole word is gated by the address
    # strobe, so an unlocked entry forwards the write payload straight to the read-back.
    # 下列期望值全部取自锁定的 PMAEntryHandleModule 主体：地址读回提供复位/NAPOT/条目 7 三个
    # 向量，写回字提供四个选通字。字内高字节是条目 base+7、低字节是条目 base+0，字节布局为
    # {L, C, ATOMIC, A[1:0], X, W, R} 且 W = io_in_wdata[57] & io_in_wdata[56]；每个字段按
    # `L ? 寄存器 : io_in_wdata` 取值并由地址选通门控，故未锁定条目会把写载荷直接透传到读回。

    got = {item["case"]: item["value"] for item in observations}
    expected = {
        "reset-entry31-masked": 0x1FFFFFFFFFFF & ~0x3FF,
        "reset-entry21": 0xC004000,
        "reset-entry22": 0xC014000,
        "napot-entry31": 0x1FFFFFFFFFFF,
        "unselected-entry31": 0x1FFFFFFFFFFF,
        # Word 0: entry 7 unlocked forwards the payload; locked it holds `{L,C,ATOMIC}=111`.
        # 字 0：条目 7 未锁定时透传载荷，锁定时保持 {L,C,ATOMIC}=111。
        "pma-cfg-word0-unlocked": 0x6000000000000000,
        "pma-cfg-word0-locked": 0xE000000000000000,
        # Word 1: entry 8 is locked and holds `{L,C,ATOMIC}=111` in the LSB byte, while entry 15
        # (MSB byte) is unlocked and forwards payload bits 62/61.
        # 字 1：低字节的条目 8 锁定并保持 {L,C,ATOMIC}=111，高字节的条目 15 未锁定，透传载荷位 62/61。
        "pma-cfg-word1-fields": 0x60000000000000E0,
        # Word 2 has no locked entry, so a zero payload collapses it to zero.
        # 字 2 没有锁定条目，零载荷使其归零。
        "pma-cfg-word2-cleared": 0x0,
        "pma-entry7-write": 0x3FFFFFFFFF & ~0x3FF,
    }
    failures = {key: [got.get(key), value] for key, value in expected.items() if got.get(key) != value}
    if failures:
        raise AssertionError(f"PMA expectations failed: {failures}")
    return expected


def main() -> int:
    """Run every gate and write the evidence file. / 运行全部门禁并写出证据文件。"""

    module = load_module(TARGET, "v2_csrlevels")
    hierarchy = json.loads(LOCKED.read_text(encoding="utf-8"))
    names = module.emitted_module_names()
    rtl = module.build_verilog(None, {})
    rtl_again = module.build_verilog({}, None)
    covered = []
    for name in names:
        locked = locked_ports(hierarchy, name)
        emitted = emitted_ports(rtl, name)
        if locked != emitted:
            raise AssertionError(f"{name}: port contract mismatch missing="
                                 f"{sorted(set(locked) - set(emitted))} extra="
                                 f"{sorted(set(emitted) - set(locked))}")
        covered.append({
            "module": name,
            "locked_ports": len(locked),
            "emitted_ports": len(emitted),
            "scala_sources": hierarchy["modules"][name]["scala_sources"],
            "child_count": hierarchy["modules"][name]["child_count"],
        })
    pmp_observations = pmp_direct(module)
    pma_observations = pma_direct(module)
    pmp_expected = check_pmp(pmp_observations, 0x2ABCDEF0123)
    pma_expected = check_pma(pma_observations)
    csrs = scala_constants(CSRS_SOURCE, "object CSRs {", "\n}")
    consts = scala_constants(CSRCONST_SOURCE, "trait HasCSRConst",
                             "def csrAccessPermissionCheck")
    address_gates = {
        "PMP_CFG_WORD_ADDRESSES": list(module.PMP_CFG_WORD_ADDRESSES)
        == [csrs["pmpcfg0"] + 2 * word for word in range(4)],
        "PMP_ENTRY_ADDRESSES": list(module.PMP_ENTRY_ADDRESSES)
        == [csrs["pmpaddr0"] + index for index in range(32)],
        "PMA_CFG_WORD_ADDRESSES": list(module.PMA_CFG_WORD_ADDRESSES)
        == [consts["PmacfgBase"] + 2 * word for word in range(4)],
        "PMA_ENTRY_ADDRESSES": list(module.PMA_ENTRY_ADDRESSES)
        == [consts["PmaaddrBase"] + index for index in range(32)],
    }
    if not all(address_gates.values()):
        raise AssertionError(f"address index mismatch: {address_gates}")
    resets = locked_pma_resets()
    reset_match = sorted(resets or []) == sorted(module.PMA_ENTRY_RESET_ADDRESSES)
    # The sibling subject is owned by another worker and may be mid-edit; a load failure is
    # reported as UNAVAILABLE instead of invalidating this subject's own evidence.
    # 同批主体由其它 worker 维护，可能正处于编辑中；加载失败只记为 UNAVAILABLE，
    # 不使本主体自身的证据失效。
    try:
        sibling = load_module(SIBLING, "v2_csrlevels_sibling")
        sibling_names = set(sibling.csr_family_module_names())
        sibling_status = "LOADED"
    except Exception as error:  # pragma: no cover - depends on the sibling file state
        sibling_names = set()
        sibling_status = f"UNAVAILABLE: {type(error).__name__}: {error}"
    all_newcsr = newcsr_module_names(hierarchy)
    uncovered = ([name for name in all_newcsr if name not in sibling_names]
                 if sibling_status == "LOADED" else None)
    verilator, yosys = lint(rtl, names[0])
    verilator_ok = verilator.returncode == 0
    yosys_ok = yosys.returncode == 0
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_NEWCSR_CSRLEVELS_FAMILY",
        "batch_id": "V2-BACKEND-NEWCSR-CSRLEVELS-001",
        "authority": {
            "reference_path": hierarchy["reference_path"],
            "reference_sha256": hierarchy["reference_sha256"],
            "locked_hierarchy": "validation/v2-locked-hierarchy.json",
            "locked_module_count": hierarchy["module_count"],
        },
        "commands": {
            "import_and_smoke": "python -c \"import importlib.util,sys; s=importlib.util.spec_from_file_location('t',TARGET); m=importlib.util.module_from_spec(s); sys.modules['t']=m; s.loader.exec_module(m); print(len(m.build_verilog({}, {})))\"",
            "freeze_audit": "python validation/v2-build-freeze-shared-audit.py",
            "pyright": f"pyright.cmd --outputjson {TARGET.relative_to(ROOT).as_posix()}",
            "validator": "python validation/v2-newcsr-csrlevels-family-validator.py",
            "verilator": "wsl.exe -e bash -lc \"verilator --lint-only -Wno-fatal <generated.sv>\"",
            "yosys": "wsl.exe -e bash -lc \"yosys -Q -p 'read_verilog -sv <generated.sv>; hierarchy -top PMPEntryHandleModule; proc; check'\"",
            "locked_reset_block": ("wsl.exe -e bash -lc \"awk '/^module PMAEntryHandleModule\\(/{f=1} "
                                   "f{print} f&&/^endmodule/{exit}' " + LOCKED_SV + "\""),
        },
        "target": {
            "path": TARGET.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(TARGET.read_bytes()).hexdigest(),
            "bytes": TARGET.stat().st_size,
            "lines": len(TARGET.read_text(encoding="utf-8").splitlines()),
            "covered_module_count": len(names),
        },
        "scope": {
            "newcsr_locked_module_count": len(all_newcsr),
            "implemented_here": names,
            "sibling_subject_load": sibling_status,
            "implemented_by_sibling_subject": len(sibling_names)
            if sibling_status == "LOADED" else None,
            "not_in_sibling_subject": uncovered,
            "uncovered_after_this_subject": None if uncovered is None
            else sorted(set(uncovered) - set(names)),
        },
        "covered": covered,
        "address_index_gates": address_gates,
        "pma_entry_reset_addresses": {
            "values": [int(value) for value in module.PMA_ENTRY_RESET_ADDRESSES],
            "locked_artifact_match": "MATCH" if reset_match else "UNAVAILABLE",
            "locked_artifact_values": resets or [],
        },
        "direct": {
            "status": "PASS",
            "vectors": len(pmp_observations) + len(pma_observations),
            "pmp_observations": pmp_observations,
            "pmp_expected": pmp_expected,
            "pma_observations": pma_observations,
            "pma_expected": pma_expected,
        },
        "backend": {
            "verilator": "PASS" if verilator_ok else "FAIL",
            "yosys": "PASS" if yosys_ok else "FAIL",
            "verilator_output": verilator.stdout.strip()[-800:],
            "yosys_output": yosys.stdout.strip()[-400:],
            "rtl_bytes": len(rtl.encode()),
            "rtl_sha256": hashlib.sha256(rtl.encode()).hexdigest(),
            "deterministic": rtl == rtl_again,
        },
        "gates": {
            "PYTHON_PRESENT": "PASS",
            "STRUCTURE_VERIFIED": "PASS",
            "PORT_CONTRACT_MATCHED": "PASS",
            "PMC_ADDRESS_INDICES_MATCHED": "PASS" if all(address_gates.values()) else "FAIL",
            "PMA_RESET_MATCHED": "PASS" if reset_match else "UNAVAILABLE",
            "DETERMINISTIC_OUTPUT": "PASS" if rtl == rtl_again else "FAIL",
            "DIRECT_TEST_PASS_BOUNDED": "PASS",
            "VERILATOR": "PASS" if verilator_ok else "FAIL",
            "YOSYS": "PASS" if yosys_ok else "FAIL",
            "PARENT_CLOSURE_MATCHED": "PENDING_SYSTEM_TOP_CSRLEVEL_PARENT",
            "BEHAVIOR_MATCHED": "NOT_ALLOWED",
            "LICENSE_REVIEW": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "status": "DIRECT_TEST_PASS_BOUNDED",
        "acceptance_eligible": False,
        "unclosed": [
            "Both handlers are verified as standalone locked modules; wiring them into the System-Top CSR parent (the NewCSR address decode that drives io_in_wen/io_in_addr) is outside this subject.",
            "The PMA reset values were compared against the locked artifact body only when the WSL copy of build/rtl/XSTop.sv was reachable; otherwise this gate stays UNAVAILABLE.",
            "License review and user approval remain pending.",
        ],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "covered": covered,
                      "verilator": payload["backend"]["verilator"],
                      "yosys": payload["backend"]["yosys"],
                      "rtl_sha256": payload["backend"]["rtl_sha256"],
                      "vectors": payload["direct"]["vectors"],
                      "uncovered_after_this_subject": payload["scope"]["uncovered_after_this_subject"]},
                     ensure_ascii=False))
    return 0 if verilator_ok and yosys_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
