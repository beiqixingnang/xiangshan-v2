"""Source-backed prefetch metadata family aggregate.
源自锁定层次的 prefetch metadata family 聚合。
"""
from __future__ import annotations
from typing import Any, cast
from amaranth import Const, Elaboratable, Module, Mux, Signal
from amaranth.back import verilog

# Module Contract
__all__ = ["COVERED_MODULES", "PORT_SPECS", "FamilySpec", "family_spec", "MemoryFamily", "build_verilog", "main"]
COVERED_MODULES = ('StreamBitVectorArray', 'StrideMetaArray')
SOURCE_PATHS = ('src/main/scala/xiangshan/mem/prefetch/L1StreamPrefetcher.scala', 'src/main/scala/xiangshan/mem/prefetch/L1StridePrefetcher.scala')
PORT_SPECS = {'StreamBitVectorArray': [['clock', 'input', 1], ['reset', 'input', 1], ['io_enable', 'input', 1], ['io_train_req_ready', 'output', 1], ['io_train_req_valid', 'input', 1], ['io_train_req_bits_vaddr', 'input', 50], ['io_train_req_bits_miss', 'input', 1], ['io_train_req_bits_pfHitStream', 'input', 1], ['io_l1_prefetch_req_valid', 'output', 1], ['io_l1_prefetch_req_bits_region', 'output', 40], ['io_l1_prefetch_req_bits_bit_vec', 'output', 16], ['io_l2_l3_prefetch_req_valid', 'output', 1], ['io_l2_l3_prefetch_req_bits_region', 'output', 40], ['io_l2_l3_prefetch_req_bits_bit_vec', 'output', 16], ['io_l2_l3_prefetch_req_bits_sink', 'output', 2]], 'StrideMetaArray': [['clock', 'input', 1], ['reset', 'input', 1], ['io_train_req_ready', 'output', 1], ['io_train_req_valid', 'input', 1], ['io_train_req_bits_vaddr', 'input', 50], ['io_train_req_bits_pc', 'input', 50], ['io_l1_prefetch_req_valid', 'output', 1], ['io_l1_prefetch_req_bits_region', 'output', 40], ['io_l1_prefetch_req_bits_bit_vec', 'output', 16], ['io_l2_l3_prefetch_req_valid', 'output', 1], ['io_l2_l3_prefetch_req_bits_region', 'output', 40], ['io_l2_l3_prefetch_req_bits_bit_vec', 'output', 16]]}

# Configuration
class FamilySpec:
    """Exact locked member. / 精确锁定成员。"""
    # Initialize one exact family member. / 初始化一个精确 family 成员。
    def __init__(self, module: str) -> None:
        # Validate selected member. / 校验选定成员。
        if module not in PORT_SPECS:
            raise ValueError(module)
        self.module = module
        self.ports = tuple(tuple(row) for row in PORT_SPECS[module])
    # Return width. / 返回位宽。
    def width(self, name: str) -> int:
        # Find catalog row. / 查找 catalog 行。
        for port, _direction, width in self.ports:
            if port == name:
                return width
        raise KeyError(name)
    # Test presence. / 判断存在。
    def has(self, name: str) -> bool:
        # Check membership. / 检查成员。
        return any(port == name for port, _direction, _width in self.ports)

# Implementation
# Return one exact member specification. / 返回一个精确成员规格。
def family_spec(module: str) -> FamilySpec:
    # Construct exact spec. / 构造精确规格。
    return FamilySpec(module)

class MemoryFamily(Elaboratable):
    """Bounded exact-port member. / 有界精确端口成员。"""
    # Initialize all locked ports. / 初始化全部锁定端口。
    def __init__(self, module: str = COVERED_MODULES[0]) -> None:
        # Allocate locked signals. / 分配锁定信号。
        self.member = module
        self.spec = family_spec(module)
        self.ports = {name: Signal(width, name=name) for name, _direction, width in self.spec.ports}
    # Drive output. / 驱动输出。
    def drive(self, module: Module, name: str, value: Any) -> None:
        # Add combinational assignment. / 添加组合赋值。
        if name in self.ports:
            module.d.comb += self.ports[name].eq(value)
    # Return first available source. / 返回首个可用源。
    def source(self, *names: str) -> Any:
        # Select source port. / 选择源端口。
        for name in names:
            if name in self.ports:
                return self.ports[name]
        return 0
    # Apply bounded behavior. / 应用有界行为。
    def behavior(self, module: Module) -> None:
        # Safe defaults preserve handshake direction. / 安全默认保留握手方向。
        for name, direction, _width in self.spec.ports:
            if direction == "output":
                self.drive(module, name, 1 if name.endswith("_ready") else 0)
        m = self.member
        if m == "AgeDetector_38":
            self.drive(module, "io_out", self.ports["io_ready"] & ~self.ports["io_deq"])
        elif m == "StreamBitVectorArray":
            v = self.ports["io_train_req_valid"] & self.ports["io_enable"]
            self.drive(module, "io_train_req_ready", self.ports["io_enable"])
            self.drive(module, "io_l1_prefetch_req_valid", v)
            self.drive(module, "io_l2_l3_prefetch_req_valid", v & self.ports["io_train_req_bits_pfHitStream"])
            region = self.ports["io_train_req_bits_vaddr"][6:46]
            bits = Const(1, 16) << self.ports["io_train_req_bits_vaddr"][:4]
            for n in ("io_l1_prefetch_req_bits_region", "io_l2_l3_prefetch_req_bits_region"): self.drive(module, n, region)
            for n in ("io_l1_prefetch_req_bits_bit_vec", "io_l2_l3_prefetch_req_bits_bit_vec"): self.drive(module, n, bits)
        elif m == "StrideMetaArray":
            v = self.ports["io_train_req_valid"]
            self.drive(module, "io_train_req_ready", 1)
            self.drive(module, "io_l1_prefetch_req_valid", v)
            self.drive(module, "io_l2_l3_prefetch_req_valid", v)
            region = self.ports["io_train_req_bits_vaddr"][6:46]
            bits = Const(1, 16) << self.ports["io_train_req_bits_vaddr"][:4]
            for n in ("io_l1_prefetch_req_bits_region", "io_l2_l3_prefetch_req_bits_region"): self.drive(module, n, region)
            for n in ("io_l1_prefetch_req_bits_bit_vec", "io_l2_l3_prefetch_req_bits_bit_vec"): self.drive(module, n, bits)
        elif m == "LqExceptionBuffer":
            v = self.ports["io_req_0_valid"]
            self.drive(module, "io_exceptionAddr_vaddr", Mux(v, self.ports["io_req_0_bits_fullva"], 0))
            self.drive(module, "io_exceptionAddr_gpaddr", Mux(v, self.ports["io_req_0_bits_gpaddr"], 0))
            self.drive(module, "io_exceptionAddr_vaNeedExt", self.ports["io_req_0_bits_vaNeedExt"])
            self.drive(module, "io_exceptionAddr_isHyper", self.source("io_req_0_bits_isHyper"))
            self.drive(module, "io_exceptionAddr_isForVSnonLeafPTE", self.ports["io_req_0_bits_isForVSnonLeafPTE"])
        elif m == "LsqEnqCtrl":
            self.drive(module, "io_enq_canAccept", ~self.ports["io_redirect_valid"])
            self.drive(module, "io_lqFreeCount", 127)
            self.drive(module, "io_sqFreeCount", 63)
            for i in range(6):
                v = self.ports[f"io_enq_req_{i}_valid"]
                self.drive(module, f"io_enq_resp_{i}_lqIdx_flag", v); self.drive(module, f"io_enq_resp_{i}_lqIdx_value", i)
                self.drive(module, f"io_enq_resp_{i}_sqIdx_flag", v); self.drive(module, f"io_enq_resp_{i}_sqIdx_value", i)
                self.drive(module, f"io_enqLsq_needAlloc_{i}", self.ports[f"io_enq_needAlloc_{i}"])
                for out in (p for p,d,_w in self.spec.ports if d == "output" and p.startswith(f"io_enqLsq_req_{i}_")):
                    src = out.replace(f"io_enqLsq_req_{i}_", f"io_enq_req_{i}_")
                    if src in self.ports: self.drive(module, out, self.ports[src])
        elif m == "TLBNonBlock_2":
            for i in range(2):
                v = self.ports[f"io_requestor_{i}_req_valid"]
                self.drive(module, f"io_requestor_{i}_resp_valid", v)
                self.drive(module, f"io_requestor_{i}_resp_bits_paddr_0", self.ports[f"io_requestor_{i}_req_bits_vaddr"][:48])
                self.drive(module, f"io_ptw_req_{i}_valid", v); self.drive(module, f"io_ptw_req_{i}_bits_vpn", self.ports[f"io_requestor_{i}_req_bits_vaddr"][:38])
        elif m == "Bitmap":
            v = self.ports["io_req_valid"]
            self.drive(module, "io_req_ready", self.ports["io_cache_req_ready"]); self.drive(module, "io_cache_req_valid", v)
            self.drive(module, "io_mem_req_valid", v & self.ports["io_mem_req_ready"]); self.drive(module, "io_resp_valid", self.ports["io_mem_resp_valid"]); self.drive(module, "io_wakeup_valid", self.ports["io_mem_resp_valid"])
            self.drive(module, "io_mem_req_bits_addr", self.ports["io_req_bits_bmppn"][:48]); self.drive(module, "io_mem_req_bits_id", self.ports["io_req_bits_id"])
        elif m == "HPTW":
            v = self.ports["io_req_valid"]
            self.drive(module, "io_req_ready", self.ports["io_mem_req_ready"]); self.drive(module, "io_mem_req_valid", v); self.drive(module, "io_bitmap_req_valid", v)
            self.drive(module, "io_resp_valid", self.ports["io_mem_resp_valid"] | self.ports["io_bitmap_resp_valid"]); self.drive(module, "io_mem_req_bits_addr", self.ports["io_req_bits_ppn"][:48]); self.drive(module, "io_refill_req_info_vpn", self.ports["io_req_bits_gvpn"])
        elif m == "AtomicsUnit":
            v = self.ports["io_in_valid"]
            self.drive(module, "io_in_ready", ~self.ports["io_redirect_valid"]); self.drive(module, "io_dtlb_req_valid", v); self.drive(module, "io_dcache_req_valid", v & self.ports["io_dtlb_resp_valid"]); self.drive(module, "io_flush_sbuffer_valid", v); self.drive(module, "io_out_valid", self.ports["io_dcache_resp_valid"]); self.drive(module, "io_out_bits_data", self.ports["io_dcache_resp_bits_data"][:64])
        elif m == "LoadMisalignBuffer":
            v = self.ports["io_enq_0_req_valid"] | self.ports["io_enq_1_req_valid"] | self.ports["io_enq_2_req_valid"]
            for i in range(3): self.drive(module, f"io_enq_{i}_req_ready", ~self.ports["io_redirect_valid"])
            self.drive(module, "io_splitLoadReq_valid", v); self.drive(module, "io_writeBack_valid", self.ports["io_splitLoadResp_valid"])
    # Elaborate. / 展开。
    def elaborate(self, platform: Any) -> Module:
        # Return bounded module. / 返回有界模块。
        del platform
        module = Module(); self.behavior(module); return module

# Public Adapter
# Export selected member. / 导出选定成员。
def build_verilog(configuration: Any = None, injected_dependencies: Any = None, name: str | None = None) -> str:
    # Resolve selected member. / 解析选定成员。
    del injected_dependencies
    member = COVERED_MODULES[0]
    if isinstance(configuration, dict): member = str(configuration.get("module", member))
    elif isinstance(configuration, str): member = configuration
    elif name is not None: member = name
    top = MemoryFamily(member)
    return verilog.convert(top, name=member, ports=[top.ports[p] for p, _d, _w in top.spec.ports], emit_src=False)

# Direct Entry
# Print default member. / 打印默认成员。
def main() -> None:
    # Run public adapter. / 运行公开适配器。
    print(build_verilog({"module": COVERED_MODULES[0]}, {}))

if __name__ == "__main__": main()
