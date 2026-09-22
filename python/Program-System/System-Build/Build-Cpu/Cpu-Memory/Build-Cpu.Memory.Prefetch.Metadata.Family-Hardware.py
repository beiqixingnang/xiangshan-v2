"""Stateful prefetch metadata family aggregate.
有状态 prefetch metadata family 聚合。
"""
from __future__ import annotations
from typing import Any, cast
from amaranth import (Array, ClockDomain, ClockSignal, Const, Elaboratable,
                      Module, Mux, ResetSignal, Signal)
from amaranth.back import verilog

# Module Contract
__all__ = ["COVERED_MODULES", "IMPLEMENTED_MEMBERS", "CONTRACT_ONLY_MEMBERS", "PORT_SPECS", "FamilySpec", "family_spec", "MemoryFamily", "build_verilog", "main"]
COVERED_MODULES = ('StreamBitVectorArray', 'StrideMetaArray')
IMPLEMENTED_MEMBERS: tuple[str, ...] = ()
CONTRACT_ONLY_MEMBERS = COVERED_MODULES
# CONTRACT_ONLY: these bounded CAMs are not promoted to behavioral equivalence
# until locked-reference differential evidence covers all replacement/training paths.
PortSpec = tuple[str, str, int]

PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    'StreamBitVectorArray': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_enable', 'input', 1),
        ('io_train_req_ready', 'output', 1),
        ('io_train_req_valid', 'input', 1),
        ('io_train_req_bits_vaddr', 'input', 50),
        ('io_train_req_bits_miss', 'input', 1),
        ('io_train_req_bits_pfHitStream', 'input', 1),
        ('io_l1_prefetch_req_valid', 'output', 1),
        ('io_l1_prefetch_req_bits_region', 'output', 40),
        ('io_l1_prefetch_req_bits_bit_vec', 'output', 16),
        ('io_l2_l3_prefetch_req_valid', 'output', 1),
        ('io_l2_l3_prefetch_req_bits_region', 'output', 40),
        ('io_l2_l3_prefetch_req_bits_bit_vec', 'output', 16),
        ('io_l2_l3_prefetch_req_bits_sink', 'output', 2),
    ),
    'StrideMetaArray': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('io_train_req_ready', 'output', 1),
        ('io_train_req_valid', 'input', 1),
        ('io_train_req_bits_vaddr', 'input', 50),
        ('io_train_req_bits_pc', 'input', 50),
        ('io_l1_prefetch_req_valid', 'output', 1),
        ('io_l1_prefetch_req_bits_region', 'output', 40),
        ('io_l1_prefetch_req_bits_bit_vec', 'output', 16),
        ('io_l2_l3_prefetch_req_valid', 'output', 1),
        ('io_l2_l3_prefetch_req_bits_region', 'output', 40),
        ('io_l2_l3_prefetch_req_bits_bit_vec', 'output', 16),
    ),
}



# Configuration
class FamilySpec:
    """Exact locked member. / 精确锁定成员。"""
    # Initialize one exact family member. / 初始化一个精确 family 成员。
    def __init__(self, module: str) -> None:
        # Validate selected member. / 校验选定成员。
        if module not in PORT_SPECS:
            raise ValueError(module)
        self.module = module
        self.ports: tuple[PortSpec, ...] = PORT_SPECS[module]
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
    """Bounded exact-port member; CONTRACT_ONLY pending locked differential. / 有界精确端口成员；锁定差分前标记 CONTRACT_ONLY。"""
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
    # Implement the stream metadata CAM. / 实现 stream 元数据 CAM。
    def _stream_behavior(self, module: Module) -> None:
        p = self.ports
        valid = [Signal(name=f"stream_valid_{i}", reset=0) for i in range(16)]
        tags = [Signal(40, name=f"stream_tag_{i}", reset=0) for i in range(16)]
        vectors = [Signal(16, name=f"stream_bits_{i}", reset=0) for i in range(16)]
        counts = [Signal(5, name=f"stream_count_{i}", reset=0) for i in range(16)]
        replacement = Signal(4, name="stream_replacement", reset=0)
        fire = p["io_train_req_valid"] & p["io_enable"]
        region = p["io_train_req_bits_vaddr"][6:46]
        one_hot = Const(1, 16) << p["io_train_req_bits_vaddr"][:4]
        hits = [valid[i] & (tags[i] == region) for i in range(16)]
        hit_any = Const(0, 1)
        hit_index = replacement
        for i in range(16):
            hit_index = Mux(hits[i] & ~hit_any, i, hit_index)
            hit_any = hit_any | hits[i]
        selected_vec = Array(vectors)[hit_index]
        selected_count = Array(counts)[hit_index]
        selected_active = Array(valid)[hit_index] & ((selected_count >= 12) | (selected_vec & one_hot != 0))
        module.d.comb += [p["io_train_req_ready"].eq(p["io_enable"]),
                          p["io_l1_prefetch_req_valid"].eq(fire & selected_active),
                          p["io_l2_l3_prefetch_req_valid"].eq(fire & selected_active & p["io_train_req_bits_pfHitStream"]),
                          p["io_l1_prefetch_req_bits_region"].eq(region),
                          p["io_l2_l3_prefetch_req_bits_region"].eq(region),
                          p["io_l1_prefetch_req_bits_bit_vec"].eq(selected_vec | one_hot),
                          p["io_l2_l3_prefetch_req_bits_bit_vec"].eq(selected_vec | one_hot),
                          p["io_l2_l3_prefetch_req_bits_sink"].eq(Mux(fire & selected_active, 1, 0))]
        with cast(Any, module.If(p["reset"])):
            module.d.sync += replacement.eq(0)
            for i in range(16):
                module.d.sync += [valid[i].eq(0), tags[i].eq(0), vectors[i].eq(0), counts[i].eq(0)]
        with cast(Any, module.Elif(fire)):
            module.d.sync += replacement.eq(Mux(hit_any, replacement, replacement + 1))
            for i in range(16):
                alloc = ~hit_any & (replacement == i)
                update = hits[i]
                new_count = Mux((vectors[i] & one_hot) != 0, counts[i], counts[i] + 1)
                with cast(Any, module.If(alloc)):
                    module.d.sync += [valid[i].eq(1), tags[i].eq(region), vectors[i].eq(one_hot), counts[i].eq(1)]
                with cast(Any, module.Elif(update)):
                    module.d.sync += [vectors[i].eq(vectors[i] | one_hot), counts[i].eq(new_count)]

    # Implement the ten-entry stride metadata CAM. / 实现十项 stride 元数据 CAM。
    def _stride_behavior(self, module: Module) -> None:
        p = self.ports
        valid = [Signal(name=f"stride_valid_{i}", reset=0) for i in range(10)]
        prev = [Signal(16, name=f"stride_prev_{i}", reset=0) for i in range(10)]
        stride = [Signal(16, name=f"stride_value_{i}", reset=0) for i in range(10)]
        confidence = [Signal(2, name=f"stride_conf_{i}", reset=0) for i in range(10)]
        pc_hash = [Signal(15, name=f"stride_pc_hash_{i}", reset=0) for i in range(10)]
        replacement = Signal(4, name="stride_replacement", reset=0)
        fire = p["io_train_req_valid"]
        pc = p["io_train_req_bits_pc"]
        pc_tag = (cast(Any, pc[:5]) ^ cast(Any, pc[5:10]) ^
                  cast(Any, pc[10:15]))
        vaddr = p["io_train_req_bits_vaddr"][:16]
        hits = [valid[i] & (pc_hash[i] == pc_tag) for i in range(10)]
        hit_any = Const(0, 1)
        hit_index = replacement
        for i in range(10):
            hit_index = Mux(hits[i] & ~hit_any, i, hit_index)
            hit_any = hit_any | hits[i]
        sel_stride = Array(stride)[hit_index]
        sel_conf = Array(confidence)[hit_index]
        delta = vaddr - Array(prev)[hit_index]
        stride_ok = ((delta != 0) & (delta != 1) &
                     ~cast(Any, delta[15]))
        stride_match = delta == sel_stride
        emit = fire & hit_any & stride_ok & stride_match & (sel_conf == 3)
        l1_addr = p["io_train_req_bits_vaddr"] + (sel_stride << 1)
        l2_addr = p["io_train_req_bits_vaddr"] + (sel_stride << 5)
        l1_bits = Const(1, 16) << l1_addr[:4]
        l2_bits = Const(1, 16) << l2_addr[:4]
        module.d.comb += [p["io_train_req_ready"].eq(1),
                          p["io_l1_prefetch_req_valid"].eq(emit),
                          p["io_l2_l3_prefetch_req_valid"].eq(emit),
                          p["io_l1_prefetch_req_bits_region"].eq(l1_addr[6:46]),
                          p["io_l2_l3_prefetch_req_bits_region"].eq(l2_addr[6:46]),
                          p["io_l1_prefetch_req_bits_bit_vec"].eq(l1_bits),
                          p["io_l2_l3_prefetch_req_bits_bit_vec"].eq(l2_bits)]
        with cast(Any, module.If(p["reset"])):
            module.d.sync += replacement.eq(0)
            for i in range(10):
                module.d.sync += [valid[i].eq(0), prev[i].eq(0), stride[i].eq(0), confidence[i].eq(0), pc_hash[i].eq(0)]
        with cast(Any, module.Elif(fire)):
            module.d.sync += replacement.eq(Mux(hit_any, replacement, Mux(replacement == 9, 0, replacement + 1)))
            for i in range(10):
                alloc = ~hit_any & (replacement == i)
                update = hits[i]
                new_delta = vaddr - prev[i]
                valid_delta = ((new_delta != 0) & (new_delta != 1) &
                               ~cast(Any, new_delta[15]))
                match_delta = new_delta == stride[i]
                with cast(Any, module.If(alloc)):
                    module.d.sync += [valid[i].eq(1), prev[i].eq(vaddr), stride[i].eq(0), confidence[i].eq(0), pc_hash[i].eq(pc_tag)]
                with cast(Any, module.Elif(update)):
                    module.d.sync += prev[i].eq(vaddr)
                    with cast(Any, module.If(valid_delta & match_delta & (confidence[i] != 3))):
                        module.d.sync += confidence[i].eq(confidence[i] + 1)
                    with cast(Any, module.Elif(valid_delta & ~match_delta)):
                        module.d.sync += confidence[i].eq(Mux(confidence[i] == 0, 0, confidence[i] - 1))
                        with cast(Any, module.If(confidence[i] <= 1)):
                            module.d.sync += stride[i].eq(new_delta)
    # Elaborate. / 展开。
    def elaborate(self, platform: Any) -> Module:
        # Elaborate the selected stateful metadata array. / 展开选定的有状态元数据阵列。
        del platform
        module = Module()
        module.domains.sync = ClockDomain("sync")
        module.d.comb += [ClockSignal("sync").eq(self.ports["clock"]),
                          ResetSignal("sync").eq(self.ports["reset"])]
        if self.member == "StreamBitVectorArray":
            self._stream_behavior(module)
        else:
            self._stride_behavior(module)
        return module

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
