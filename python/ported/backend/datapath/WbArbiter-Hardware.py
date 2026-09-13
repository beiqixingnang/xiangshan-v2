"""WbArbiter (write-back dispatcher, collide checker and WbDataPath). / 写回分发、冲突检查与写回数据通路。"""

from __future__ import annotations

from dataclasses import dataclass, field

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal
from amaranth.lib import data


# =============================================================================
# Module Contract
# =============================================================================
# Public symbols / 公开符号:
#   - WbArbiterDispatcher : 1->n fanout by accept condition
#   - RealWBCollideChecker : per-port RealWBArbiter collide checker
#   - WbDataPathConfig, WbDataPath : write-back datapath orchestrator
#   - build_verilog, main
# Real logic: WbArbiterDispatcher fans one input to n outputs by an accept
# vector (at most one accept; ready OR-of accepts or notWrite); RealWBCollide-
# Checker groups inputs by write port and instantiates one RealWBArbiter per
# port; WbDataPath splits exu outputs by regfile write flags, drives per-
# regtype RealWBCollideCheckers, and emits toPreg/toCtrlBlock. VldMergeUnit
# injection and NewExuOutput/WriteBackRFBundle plumbing are COMPRESSED.
# / 真实逻辑：WbArbiterDispatcher 按接受向量将单输入扇出到 n（至多一个接受；
# 就绪为接受或非写）；RealWBCollideChecker 按写口分组每口一个 RealWBArbiter；
# WbDataPath 按寄存器堆写标志分流 exu 输出，驱动每寄存器堆的冲突检查器并输
# 出 toPreg/toCtrlBlock。VldMergeUnit 注入与束接线压缩。
# depends on Build-Cpu.Backend.Datapath.RFWBConflictChecker (RealWBArbiter mirrored locally)
# depends on Build-Cpu.Backend.Datapath.VldMergeUnit (injected for vec schd)
# Status / 状态: PYTHON_PRESENT_UNVERIFIED (phase-1 bulk port / 阶段一批量重写)
__all__ = ["WbArbiterDispatcher", "RealWBCollideChecker",
           "WbDataPathConfig", "WbDataPath", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
@dataclass(frozen=True)
class WbExuAttr:
    # per-exu write-back attributes / 每 exu 写回属性
    name: str
    writeIntRf: bool
    writeFpRf: bool
    writeVfRf: bool
    writeV0Rf: bool
    writeVlRf: bool
    hasUncertainLatency: bool
    hasNoDataWB: bool
    isHighestWBPriority: bool
    isVfExeUnit: bool
    isFpExeUnit: bool
    hasVLoadFu: bool


@dataclass(frozen=True)
class WbDataPathConfig:
    # write-back datapath configuration / 写回数据通路配置
    # per-scheduler exu attributes / 每调度器 exu 属性
    intExus: tuple
    fpExus: tuple
    vfExus: tuple
    # per-regtype collide-checker port lists (port ids per exu per src) /
    # 每寄存器堆冲突检查端口列表（每 exu 每 src 的口 id）
    intWbPorts: tuple
    fpWbPorts: tuple
    vfWbPorts: tuple
    v0WbPorts: tuple
    vlWbPorts: tuple
    intPortMax: int
    fpPortMax: int
    vfPortMax: int
    v0PortMax: int
    vlPortMax: int
    isVecSchd: bool
    dataWidth: int = 64
    addrWidth: int = 8
    RobPtrWidth: int = 10


# =============================================================================
# Implementation
# =============================================================================
# Compute one-hot first-true grants / 计算首个真请求的独热授权
def arbiterCtrl(request):
    # one-hot first-true grant / 首真独热授权
    n = len(request)
    if n == 0:
        return []
    if n == 1:
        return [Const(1, 1)]
    scanned = [request[0]]
    cur = request[0]
    for r in request[1:-1]:
        cur = cur | r
        scanned.append(cur)
    return [request[0]] + [~s for s in scanned]


class RealWBArbiter(Elaboratable):
    # simple priority arbiter (mirrored locally) / 简单优先仲裁（本地镜像）
    def __init__(self, dataWidth=64, n=2):
        self.dataWidth = dataWidth
        self.n = n
        self.in_valid = [Signal(name=f"in_valid_{i}") for i in range(n)]
        self.in_ready = [Signal(name=f"in_ready_{i}") for i in range(n)]
        self.in_bits = [Signal(dataWidth, name=f"in_bits_{i}") for i in range(n)]
        self.out_valid = Signal(name="out_valid")
        self.out_ready = Signal(name="out_ready")
        self.out_bits = Signal(dataWidth, name="out_bits")
        self.chosen = Signal(max(1, n.bit_length()), name="chosen")

    # Elaborate the priority arbiter datapath / 展开优先级仲裁数据通路
    def elaborate(self, platform):
        # build the simple arbiter / 构建简单仲裁器
        m = Module()
        n = self.n
        m.d.comb += self.chosen.eq(n - 1)
        m.d.comb += self.out_bits.eq(self.in_bits[n - 1])
        for i in range(n - 2, -1, -1):
            with m.If(self.in_valid[i]):
                m.d.comb += self.chosen.eq(i)
                m.d.comb += self.out_bits.eq(self.in_bits[i])
        grant = arbiterCtrl(self.in_valid)
        for i in range(n):
            m.d.comb += self.in_ready[i].eq((grant[i] | ~self.in_valid[i]) &
                                            self.out_ready)
        m.d.comb += self.out_valid.eq(~grant[-1] | self.in_valid[-1])
        return m


class WbArbiterDispatcher(Elaboratable):
    # 1->n fanout by accept vector / 按接受向量扇出
    def __init__(self, dataWidth=64, n=5):
        self.dataWidth = dataWidth
        self.n = n
        self.in_valid = Signal(name="in_valid")
        self.in_ready = Signal(name="in_ready")
        self.in_bits = Signal(dataWidth, name="in_bits")
        # per-output accept + write flags from bits / 每输出接受位与写标志
        self.acceptVec = [Signal(name=f"accept_{i}") for i in range(n)]
        self.notWrite = Signal(name="notWrite")
        self.out_valid = [Signal(name=f"out_valid_{i}") for i in range(n)]
        self.out_ready = [Signal(name=f"out_ready_{i}") for i in range(n)]
        self.out_bits = [Signal(dataWidth, name=f"out_bits_{i}") for i in range(n)]

    # Elaborate fanout and ready propagation / 展开扇出与就绪传播
    def elaborate(self, platform):
        # build the dispatcher / 构建分发器
        m = Module()
        n = self.n
        for i in range(n):
            m.d.comb += self.out_valid[i].eq(self.acceptVec[i] & self.in_valid)
            m.d.comb += self.out_bits[i].eq(self.in_bits)
        readyOr = Const(0, 1)
        for i in range(n):
            readyOr = readyOr | (self.out_ready[i] & self.acceptVec[i])
        m.d.comb += self.in_ready.eq(readyOr | self.notWrite)
        return m


class RealWBCollideChecker(Elaboratable):
    # per-port collide checker / 按口冲突检查
    def __init__(self, dataWidth=64, inPorts=(), portRange=(), portMax=0):
        self.dataWidth = dataWidth
        self.inPorts = inPorts  # flat list of port ids / 口 id 平铺
        self.inGroup = {}
        for idx, port in enumerate(inPorts):
            if port < 0:
                continue
            self.inGroup.setdefault(port, []).append(idx)
        self.arbiters = {}
        for port in portRange:
            if port in self.inGroup:
                self.arbiters[port] = RealWBArbiter(dataWidth, len(self.inGroup[port]))
        self.numIn = len(inPorts)
        self.in_valid = [Signal(name=f"in_valid_{i}") for i in range(self.numIn)]
        self.in_ready = [Signal(name=f"in_ready_{i}") for i in range(self.numIn)]
        self.in_bits = [Signal(dataWidth, name=f"in_bits_{i}") for i in range(self.numIn)]
        self.out_valid = [Signal(name=f"out_valid_{p}") for p in range(portMax + 1)]
        self.out_bits = [Signal(dataWidth, name=f"out_bits_{p}") for p in range(portMax + 1)]
        self.out_fire = [Signal(name=f"out_fire_{p}") for p in range(portMax + 1)]

    # Elaborate grouped per-port arbiters / 展开按端口分组的仲裁器
    def elaborate(self, platform):
        # build the collide checker / 构建冲突检查
        m = Module()
        for port, arb in self.arbiters.items():
            m.submodules[f"arb_{port}"] = arb
            members = self.inGroup[port]
            for k, idx in enumerate(members):
                m.d.comb += arb.in_valid[k].eq(self.in_valid[idx])
                m.d.comb += arb.in_bits[k].eq(self.in_bits[idx])
                m.d.comb += self.in_ready[idx].eq(arb.in_ready[k])
        for idx, port in enumerate(self.inPorts):
            if port < 0:
                m.d.comb += self.in_ready[idx].eq(1)
        maxP = len(self.out_valid) - 1
        for p in range(maxP + 1):
            if p in self.arbiters:
                arb = self.arbiters[p]
                m.d.comb += arb.out_ready.eq(1)
                m.d.comb += self.out_valid[p].eq(arb.out_valid)
                m.d.comb += self.out_bits[p].eq(arb.out_bits)
                m.d.comb += self.out_fire[p].eq(arb.out_valid)
            else:
                m.d.comb += self.out_valid[p].eq(0)
        return m


class WbDataPath(Elaboratable):
    # write-back datapath orchestrator / 写回数据通路编排器
    def __init__(self, config):
        self.config = config
        c = config
        allExus = list(c.intExus) + list(c.fpExus) + list(c.vfExus)
        self.allExus = allExus
        n = len(allExus)
        # exu inputs / exu 输入
        self.fromExu_valid = [Signal(name=f"fe_valid_{i}") for i in range(n)]
        self.fromExu_ready = [Signal(name=f"fe_ready_{i}") for i in range(n)]
        self.fromExu_bits = [Signal(c.dataWidth, name=f"fe_bits_{i}") for i in range(n)]
        # per-regtype write flags from bits / 每寄存器堆写标志
        self.toIntRf = [Signal(name=f"toInt_{i}") for i in range(n)]
        self.toFpRf = [Signal(name=f"toFp_{i}") for i in range(n)]
        self.toVecRf = [Signal(name=f"toVec_{i}") for i in range(n)]
        self.toV0Rf = [Signal(name=f"toV0_{i}") for i in range(n)]
        self.toVlRf = [Signal(name=f"toVl_{i}") for i in range(n)]
        # per-regtype collide checkers / 每寄存器堆冲突检查
        self.intArb = RealWBCollideChecker(c.dataWidth, c.intWbPorts,
                                           range(c.intPortMax + 1), c.intPortMax)
        self.fpArb = RealWBCollideChecker(c.dataWidth, c.fpWbPorts,
                                          range(c.fpPortMax + 1), c.fpPortMax)
        self.vfArb = RealWBCollideChecker(c.dataWidth, c.vfWbPorts,
                                          range(c.vfPortMax + 1), c.vfPortMax)
        self.v0Arb = RealWBCollideChecker(c.dataWidth, c.v0WbPorts,
                                          range(c.v0PortMax + 1), c.v0PortMax)
        self.vlArb = RealWBCollideChecker(c.dataWidth, c.vlWbPorts,
                                          range(c.vlPortMax + 1), c.vlPortMax)
        # outputs to preg / 到物理寄存器堆
        self.toIntPreg_valid = self.intArb.out_fire
        self.toIntPreg_bits = self.intArb.out_bits
        self.toFpPreg_valid = self.fpArb.out_fire
        self.toFpPreg_bits = self.fpArb.out_bits
        self.toVfPreg_valid = self.vfArb.out_fire
        self.toVfPreg_bits = self.vfArb.out_bits
        self.toV0Preg_valid = self.v0Arb.out_fire
        self.toV0Preg_bits = self.v0Arb.out_bits
        self.toVlPreg_valid = self.vlArb.out_fire
        self.toVlPreg_bits = self.vlArb.out_bits
        # to ctrl block writeback (fired exus of this schd) / 到控制块写回
        nWb = n  # one writeback per exu / 每 exu 一个写回
        self.toCtrl_writeback_valid = [Signal(name=f"tcwb_valid_{i}") for i in range(nWb)]

    # Elaborate write-back arbitration and routing / 展开写回仲裁与路由
    def elaborate(self, platform):
        # build the write-back datapath / 构建写回数据通路
        m = Module()
        c = self.config
        m.submodules.intArb = self.intArb
        m.submodules.fpArb = self.fpArb
        m.submodules.vfArb = self.vfArb
        m.submodules.v0Arb = self.v0Arb
        m.submodules.vlArb = self.vlArb
        # per-exu acceptCond + fanout to per-regtype arbiter inputs /
        # 每 exu 接受条件与扇出到各寄存器堆仲裁输入
        intIdx = 0
        fpIdx = 0
        vfIdx = 0
        v0Idx = 0
        vlIdx = 0
        for i, attr in enumerate(self.allExus):
            intWrite = self.fromExu_valid[i] & self.toIntRf[i]
            fpWrite = self.fromExu_valid[i] & self.toFpRf[i]
            vfWrite = self.fromExu_valid[i] & self.toVecRf[i]
            v0Write = self.fromExu_valid[i] & self.toV0Rf[i]
            vlWrite = self.fromExu_valid[i] & self.toVlRf[i]
            notWrite = ~(self.toIntRf[i] | self.toFpRf[i] | self.toVecRf[i] |
                         self.toV0Rf[i] | self.toVlRf[i])
            # drive arbiter inputs / 驱动仲裁输入
            if attr.writeIntRf and intIdx < len(self.intArb.in_valid):
                m.d.comb += self.intArb.in_valid[intIdx].eq(intWrite)
                m.d.comb += self.intArb.in_bits[intIdx].eq(self.fromExu_bits[i])
                intIdx += 1
            if attr.writeFpRf and fpIdx < len(self.fpArb.in_valid):
                m.d.comb += self.fpArb.in_valid[fpIdx].eq(fpWrite)
                m.d.comb += self.fpArb.in_bits[fpIdx].eq(self.fromExu_bits[i])
                fpIdx += 1
            if attr.writeVfRf and vfIdx < len(self.vfArb.in_valid):
                m.d.comb += self.vfArb.in_valid[vfIdx].eq(vfWrite)
                m.d.comb += self.vfArb.in_bits[vfIdx].eq(self.fromExu_bits[i])
                vfIdx += 1
            if attr.writeV0Rf and v0Idx < len(self.v0Arb.in_valid):
                m.d.comb += self.v0Arb.in_valid[v0Idx].eq(v0Write)
                m.d.comb += self.v0Arb.in_bits[v0Idx].eq(self.fromExu_bits[i])
                v0Idx += 1
            if attr.writeVlRf and vlIdx < len(self.vlArb.in_valid):
                m.d.comb += self.vlArb.in_valid[vlIdx].eq(vlWrite)
                m.d.comb += self.vlArb.in_bits[vlIdx].eq(self.fromExu_bits[i])
                vlIdx += 1
            # exu ready / exu 就绪
            if attr.hasUncertainLatency:
                rdy = (self.intArb.in_ready[max(0, intIdx - 1)] & intWrite if attr.writeIntRf else Const(0, 1))
                # OR of applicable arbiter readies / 适用仲裁就绪或
                acc = Const(0, 1)
                if attr.writeIntRf:
                    acc = acc | (self.intArb.in_ready[intIdx - 1] & intWrite)
                if attr.writeFpRf:
                    acc = acc | (self.fpArb.in_ready[fpIdx - 1] & fpWrite)
                if attr.writeVfRf:
                    acc = acc | (self.vfArb.in_ready[vfIdx - 1] & vfWrite)
                if attr.writeV0Rf:
                    acc = acc | (self.v0Arb.in_ready[v0Idx - 1] & v0Write)
                if attr.writeVlRf:
                    acc = acc | (self.vlArb.in_ready[vlIdx - 1] & vlWrite)
                m.d.comb += self.fromExu_ready[i].eq(acc | notWrite)
            else:
                m.d.comb += self.fromExu_ready[i].eq(1)
            if attr.hasNoDataWB or attr.isHighestWBPriority:
                m.d.comb += self.fromExu_ready[i].eq(1)
            # to ctrl block writeback: fired / 到控制块写回：出火
            m.d.comb += self.toCtrl_writeback_valid[i].eq(
                self.fromExu_valid[i] & self.fromExu_ready[i])
        return m


# =============================================================================
# Public Adapter
# =============================================================================
# Convert the dispatcher to Verilog / 将分发器转换为 Verilog
def build_verilog(dataWidth: int = 64, n: int = 5, name: str = "WbArbiterDispatcher") -> str:
    # Convert dispatcher to verilog / 转换分发器为 Verilog
    from amaranth.back import verilog

    top = WbArbiterDispatcher(dataWidth, n)
    ports = [top.in_valid, top.in_ready, top.in_bits, top.notWrite]
    ports += top.acceptVec + top.out_valid + top.out_ready + top.out_bits
    return verilog.convert(top, name=name, ports=ports)


# =============================================================================
# Direct Entry
# =============================================================================
# Run the standalone Verilog entrypoint / 运行独立 Verilog 入口
def main() -> None:
    # Entry point / 入口
    print(build_verilog())


if __name__ == "__main__":
    main()
