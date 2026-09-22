"""Stateful prefetch metadata family aggregate.
有状态 prefetch metadata family 聚合。
"""
from __future__ import annotations
from typing import Any, cast
from amaranth import (Array, Cat, ClockDomain, ClockSignal, Const,
                      Elaboratable, Module, Mux, ResetSignal, Signal)
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


def _one_hot_index(matches: list[Any], width: int) -> Any:
    """Convert a one-hot vector with the generated OR encoding."""

    result: Any = Const(0, width)
    for index, match in enumerate(matches):
        result = result | Mux(match, Const(index, width), Const(0, width))
    return result


def _region_hash(tag: Any) -> Any:
    """Return the 15-bit region hash."""

    folded = (cast(Any, tag[10:15]) ^ cast(Any, tag[15:20]) ^
              cast(Any, tag[20:25]))
    return Cat(tag[:10], folded)


def _pc_hash(pc: Any) -> Any:
    """Return the 15-bit program-counter hash."""

    folded = (cast(Any, pc[10:15]) ^ cast(Any, pc[15:20]) ^
              cast(Any, pc[20:25]))
    return Cat(pc[:10], folded)


def _plru_way(state: Any, ways: int) -> Any:
    """Decode a balanced or unbalanced tree-PLRU state."""

    if ways == 16:
        left_inner = Mux(
            state[13],
            Cat(Mux(state[12], state[11], state[10]), state[12]),
            Cat(Mux(state[9], state[8], state[7]), state[9]),
        )
        left = Cat(left_inner, state[13])
        right_inner = Mux(
            state[6],
            Cat(Mux(state[5], state[4], state[3]), state[5]),
            Cat(Mux(state[2], state[1], state[0]), state[2]),
        )
        right = Cat(right_inner, state[6])
        return Cat(Mux(state[14], left, right), state[14])
    if ways == 10:
        left = Cat(state[7], Const(0, 2))
        right_low = Mux(state[2], state[1], state[0])
        right_mid = Cat(right_low, state[2])
        right = Cat(right_mid, state[6])
        return Cat(Mux(state[8], left, right), state[8])
    if ways <= 1:
        return Const(0, 1)
    if ways == 2:
        return state[0]
    power = 1 << (ways.bit_length() - 1)
    right_ways = power >> 1
    left_ways = ways - right_ways
    root = state[ways - 2]
    left_state = state[right_ways - 1:ways - 2]
    right_state = state[:right_ways - 1]
    left_way = _plru_way(left_state, left_ways)
    right_way = _plru_way(right_state, right_ways)
    selected = Mux(root, left_way, right_way) if left_ways > 1 else Mux(root, 0, right_way)
    return Cat(selected, root)


def _plru_next(state: Any, touch: Any, ways: int) -> Any:
    """Update a tree-PLRU state after one way is touched."""

    if ways == 16:
        root = ~touch[3]
        left_state = state[7:14]
        right_state = state[:7]
        left_next = Mux(touch[3], _plru_next(left_state, touch[:3], 8), left_state)
        right_next = Mux(touch[3], right_state, _plru_next(right_state, touch[:3], 8))
        return Cat(right_next, left_next, root)
    if ways == 10:
        root = ~touch[3]
        left_state = state[7:8]
        right_state = state[:7]
        left_next = Mux(touch[3], ~touch[0], left_state)
        right_next = Mux(touch[3], right_state, _plru_next(right_state, touch[:3], 8))
        return Cat(right_next, left_next, root)
    if ways <= 1:
        return Const(0, 1)
    if ways == 2:
        return ~touch[0]
    power = 1 << (ways.bit_length() - 1)
    right_ways = power >> 1
    left_ways = ways - right_ways
    ceil_log = (ways - 1).bit_length()
    if len(touch) < ceil_log:
        touch = Cat(touch, Const(0, ceil_log - len(touch)))
    elif len(touch) > ceil_log:
        touch = touch[:ceil_log]
    root = ~touch[ceil_log - 1]
    left_state = state[right_ways - 1:ways - 2]
    right_state = state[:right_ways - 1]
    left_touch = touch[:max(1, left_ways.bit_length() - 1)]
    right_touch = touch[:max(1, right_ways.bit_length() - 1)]
    left_next = (Mux(root, left_state,
                     _plru_next(left_state, left_touch, left_ways))
                 if left_ways > 1 else left_state)
    right_next = (Mux(root,
                      _plru_next(right_state, right_touch, right_ways),
                      right_state))
    return Cat(right_next, left_next, root)

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
        tags = [Signal(40, name=f"stream_tag_{i}", reset_less=True) for i in range(16)]
        vectors = [Signal(16, name=f"stream_bits_{i}", reset_less=True) for i in range(16)]
        active = [Signal(name=f"stream_active_{i}", reset_less=True) for i in range(16)]
        counts = [Signal(5, name=f"stream_count_{i}", reset_less=True) for i in range(16)]
        replacement = Signal(15, name="stream_replacement", reset=0)
        vaddr = p["io_train_req_bits_vaddr"]
        region = vaddr[10:50]
        region_bits = vaddr[6:10]
        one_hot = Const(1, 16) << region_bits
        region_hash = _region_hash(region)
        plus_hash = _region_hash(region + Const(1, 40))
        minus_hash = _region_hash(region - Const(1, 40))
        hits = [valid[i] & p["io_train_req_valid"] & p["io_train_req_ready"] & (_region_hash(tags[i]) == region_hash)
                for i in range(16)]
        plus_hits = [valid[i] & p["io_train_req_valid"] & p["io_train_req_ready"] & (_region_hash(tags[i]) == plus_hash)
                     for i in range(16)]
        minus_hits = [valid[i] & p["io_train_req_valid"] & p["io_train_req_ready"] & (_region_hash(tags[i]) == minus_hash)
                      for i in range(16)]
        hit_any = Const(0, 1)
        plus_any = Const(0, 1)
        minus_any = Const(0, 1)
        for hit in hits:
            hit_any = hit_any | hit
        for hit in plus_hits:
            plus_any = plus_any | hit
        for hit in minus_hits:
            minus_any = minus_any | hit
        state = replacement
        replace_way = _plru_way(state, 16)
        hit_index = _one_hot_index(hits, 4)
        plus_index = _one_hot_index(plus_hits, 4)
        minus_index = _one_hot_index(minus_hits, 4)
        s0_index = Mux(hit_any, hit_index, replace_way)
        s0_valid = p["io_train_req_valid"] & p["io_train_req_ready"]
        s1_valid = Signal(name="stream_s1_valid", reset=0)
        s1_index = Signal(4, name="stream_s1_index", reset_less=True)
        s1_miss = Signal(name="stream_s1_miss", reset_less=True)
        s1_pf_hit = Signal(name="stream_s1_pf_hit", reset_less=True)
        s1_plus_index = Signal(4, name="stream_s1_plus_index", reset_less=True)
        s1_minus_index = Signal(4, name="stream_s1_minus_index", reset_less=True)
        s1_hit = Signal(name="stream_s1_hit", reset_less=True)
        s1_plus_hit = Signal(name="stream_s1_plus_hit", reset_less=True)
        s1_minus_hit = Signal(name="stream_s1_minus_hit", reset_less=True)
        s1_region = Signal(40, name="stream_s1_region", reset_less=True)
        s1_region_bits = Signal(4, name="stream_s1_region_bits", reset_less=True)
        s1_hash = _region_hash(s1_region)
        current_ready = ~(s1_valid & (s1_hash == region_hash))
        module.d.comb += p["io_train_req_ready"].eq(current_ready)
        module.d.sync += s1_valid.eq(s0_valid)
        with cast(Any, module.If(s0_valid)):
            module.d.sync += [s1_index.eq(s0_index), s1_miss.eq(p["io_train_req_bits_miss"]),
                              s1_pf_hit.eq(p["io_train_req_bits_pfHitStream"]),
                              s1_plus_index.eq(plus_index), s1_minus_index.eq(minus_index),
                              s1_hit.eq(hit_any), s1_plus_hit.eq(plus_any),
                              s1_minus_hit.eq(minus_any), s1_region.eq(region),
                              s1_region_bits.eq(region_bits)]
        selected_vector = Array(vectors)[s1_index]
        selected_count = Array(counts)[s1_index]
        selected_active = Array(active)[s1_index]
        s1_plus_active = s1_plus_hit & Array(active)[s1_plus_index] & (Array(counts)[s1_plus_index] >= 12)
        s1_minus_active = s1_minus_hit & Array(active)[s1_minus_index] & (Array(counts)[s1_minus_index] >= 12)
        s1_alloc = s1_valid & ~s1_hit
        s1_update = s1_valid & s1_hit
        s1_one_hot = Const(1, 16) << s1_region_bits
        s1_can_send = Mux(s1_update, ~((selected_vector & s1_one_hot).any()), Const(1, 1)) & (s1_miss | s1_pf_hit)
        s1_l1_base = Cat(s1_region_bits, s1_region)
        s2_valid = Signal(name="stream_s2_valid", reset=0)
        s2_index = Signal(4, name="stream_s2_index", reset_less=True)
        s2_l1_addr = Signal(50, name="stream_s2_l1_addr", reset_less=True)
        s2_l2_addr = Signal(50, name="stream_s2_l2_addr", reset_less=True)
        s2_can_send = Signal(name="stream_s2_can_send", reset_less=True)
        module.d.sync += s2_valid.eq(s1_valid)
        with cast(Any, module.If(s1_valid)):
            module.d.sync += [s2_index.eq(s1_index),
                              s2_l1_addr.eq(Cat(Const(0, 6), s1_l1_base + Const(0x40, 44))),
                              s2_l2_addr.eq(Cat(Const(0, 6), s1_l1_base + Const(0x280, 44))),
                              s2_can_send.eq(s1_can_send)]
        s2_active = Array(active)[s2_index]
        s2_pf_valid = s2_valid & s2_active & s2_can_send & p["io_enable"]
        def region_vector(address: Any, width: int) -> Any:
            base = Const(1, 16) << address[6:10]
            result: Any = Const(0, 16)
            for offset in range(width):
                result = result | (base << offset)
            return result
        s3_l1_valid = Signal(name="stream_s3_l1_valid", reset=0)
        s3_l2_valid = Signal(name="stream_s3_l2_valid", reset=0)
        s3_l1_region = Signal(40, name="stream_s3_l1_region", reset_less=True)
        s3_l1_vector = Signal(16, name="stream_s3_l1_vector", reset_less=True)
        s3_l2_region = Signal(40, name="stream_s3_l2_region", reset_less=True)
        s3_l2_vector = Signal(16, name="stream_s3_l2_vector", reset_less=True)
        s4_l2_valid = Signal(name="stream_s4_l2_valid", reset=0)
        s4_l2_region = Signal(40, name="stream_s4_l2_region", reset_less=True)
        s4_l2_vector = Signal(16, name="stream_s4_l2_vector", reset_less=True)
        s4_l3_region = Signal(40, name="stream_s4_l3_region", reset_less=True)
        s4_l3_vector = Signal(16, name="stream_s4_l3_vector", reset_less=True)
        s5_l3_region = Signal(40, name="stream_s5_l3_region", reset_less=True)
        s5_l3_vector = Signal(16, name="stream_s5_l3_vector", reset_less=True)
        module.d.sync += [s3_l1_valid.eq(s2_pf_valid), s3_l2_valid.eq(s2_pf_valid),
                          s4_l2_valid.eq(s3_l2_valid)]
        with cast(Any, module.If(s2_pf_valid)):
            module.d.sync += [s3_l1_region.eq(s2_l1_addr[10:50]),
                              s3_l1_vector.eq(region_vector(s2_l1_addr, 2)),
                              s3_l2_region.eq(s2_l2_addr[10:50]),
                              s3_l2_vector.eq(region_vector(s2_l2_addr, 4))]
        with cast(Any, module.If(s3_l2_valid)):
            module.d.sync += [s4_l2_region.eq(s3_l2_region), s4_l2_vector.eq(s3_l2_vector),
                              s4_l3_region.eq(s3_l2_region), s4_l3_vector.eq(s3_l2_vector)]
        with cast(Any, module.If(s4_l2_valid)):
            module.d.sync += [s5_l3_region.eq(s4_l3_region), s5_l3_vector.eq(s4_l3_vector)]
        module.d.comb += [p["io_l1_prefetch_req_valid"].eq(s3_l1_valid),
                          p["io_l1_prefetch_req_bits_region"].eq(s3_l1_region),
                          p["io_l1_prefetch_req_bits_bit_vec"].eq(s3_l1_vector),
                          p["io_l2_l3_prefetch_req_valid"].eq(s4_l2_valid),
                          p["io_l2_l3_prefetch_req_bits_region"].eq(Mux(s4_l2_valid, s4_l2_region, s5_l3_region)),
                          p["io_l2_l3_prefetch_req_bits_bit_vec"].eq(Mux(s4_l2_valid, s4_l2_vector, s5_l3_vector)),
                          p["io_l2_l3_prefetch_req_bits_sink"].eq(Mux(s4_l2_valid, 1, 2))]
        with cast(Any, module.If(s0_valid)):
            module.d.sync += replacement.eq(_plru_next(state, s0_index, 16))
        for i in range(16):
            alloc = s1_alloc & (s1_index == i)
            update = s1_update & (s1_index == i)
            cnt_en = ~((vectors[i] & s1_one_hot).any())
            cnt_next = Mux(cnt_en, counts[i] + 1, counts[i])
            with cast(Any, module.If(alloc)):
                module.d.sync += [valid[i].eq(1), tags[i].eq(s1_region), vectors[i].eq(s1_one_hot),
                                  counts[i].eq(1), active[i].eq(s1_plus_active | s1_minus_active)]
            with cast(Any, module.If(update)):
                module.d.sync += [vectors[i].eq(vectors[i] | s1_one_hot), counts[i].eq(cnt_next),
                                  active[i].eq(active[i] | (cnt_next >= 12) |
                                               s1_plus_active | s1_minus_active)]

    # Implement the ten-entry stride metadata CAM. / 实现十项 stride 元数据 CAM。
    def _stride_behavior(self, module: Module) -> None:
        p = self.ports
        valid = [Signal(name=f"stride_valid_{i}", reset=0) for i in range(10)]
        prev = [Signal(16, name=f"stride_prev_{i}", reset_less=True) for i in range(10)]
        stride = [Signal(16, name=f"stride_value_{i}", reset_less=True) for i in range(10)]
        confidence = [Signal(2, name=f"stride_conf_{i}", reset_less=True) for i in range(10)]
        pc_hash = [Signal(15, name=f"stride_pc_hash_{i}", reset_less=True) for i in range(10)]
        replacement = Signal(9, name="stride_replacement", reset=0)
        vaddr = p["io_train_req_bits_vaddr"]
        pc_tag = _pc_hash(p["io_train_req_bits_pc"])
        vaddr_low = vaddr[:16]
        hits = [valid[i] & p["io_train_req_valid"] & p["io_train_req_ready"] &
                (pc_hash[i] == pc_tag) for i in range(10)]
        hit_any: Any = Const(0, 1)
        for hit in hits:
            hit_any = hit_any | hit
        hit_index = _one_hot_index(hits, 4)
        s0_index = Mux(hit_any, hit_index, _plru_way(replacement, 10))
        s0_valid = p["io_train_req_valid"] & p["io_train_req_ready"]
        s1_valid = Signal(name="stride_s1_valid", reset=0)
        s1_index = Signal(4, name="stride_s1_index", reset_less=True)
        s1_hash = Signal(15, name="stride_s1_hash", reset_less=True)
        s1_vaddr = Signal(50, name="stride_s1_vaddr", reset_less=True)
        s1_hit = Signal(name="stride_s1_hit", reset_less=True)
        module.d.comb += p["io_train_req_ready"].eq(~(s1_valid & (s1_hash == pc_tag)))
        module.d.sync += s1_valid.eq(s0_valid)
        with cast(Any, module.If(s0_valid)):
            module.d.sync += [s1_index.eq(s0_index), s1_hash.eq(pc_tag),
                              s1_vaddr.eq(vaddr), s1_hit.eq(hit_any)]
        s1_alloc = s1_valid & ~s1_hit
        s1_update = s1_valid & s1_hit
        old_stride = Array(stride)[s1_index]
        old_prev = Array(prev)[s1_index]
        old_conf = Array(confidence)[s1_index]
        new_delta = s1_vaddr[:16] - old_prev
        new_block_delta = new_delta[6:16]
        stride_valid = (new_block_delta != 0) & (new_block_delta != 1) & ~cast(Any, new_delta[15])
        stride_match = new_delta == old_stride
        can_send = s1_update & stride_valid & stride_match & (old_conf == 3)
        s2_valid = Signal(name="stride_s2_valid", reset=0)
        s2_vaddr = Signal(50, name="stride_s2_vaddr", reset_less=True)
        s2_stride = Signal(16, name="stride_s2_stride", reset_less=True)
        module.d.sync += s2_valid.eq(can_send)
        with cast(Any, module.If(can_send)):
            module.d.sync += [s2_vaddr.eq(s1_vaddr), s2_stride.eq(old_stride)]
        s2_l1_addr = s2_vaddr + (s2_stride << 2)
        s2_l2_addr = s2_vaddr + (s2_stride << 5)
        s3_valid = Signal(name="stride_s3_valid", reset=0)
        s3_l1_region = Signal(40, name="stride_s3_l1_region", reset_less=True)
        s3_l1_vector = Signal(16, name="stride_s3_l1_vector", reset_less=True)
        s3_l2_region = Signal(40, name="stride_s3_l2_region", reset_less=True)
        s3_l2_vector = Signal(16, name="stride_s3_l2_vector", reset_less=True)
        s4_valid = Signal(name="stride_s4_valid", reset=0)
        s4_l2_region = Signal(40, name="stride_s4_l2_region", reset_less=True)
        s4_l2_vector = Signal(16, name="stride_s4_l2_vector", reset_less=True)
        module.d.sync += [s3_valid.eq(s2_valid), s4_valid.eq(s3_valid)]
        with cast(Any, module.If(s2_valid)):
            module.d.sync += [s3_l1_region.eq(s2_l1_addr[10:50]),
                              s3_l1_vector.eq(Const(1, 16) << s2_l1_addr[6:10]),
                              s3_l2_region.eq(s2_l2_addr[10:50]),
                              s3_l2_vector.eq(Const(1, 16) << s2_l2_addr[6:10])]
        with cast(Any, module.If(s3_valid)):
            module.d.sync += [s4_l2_region.eq(s3_l2_region), s4_l2_vector.eq(s3_l2_vector)]
        module.d.comb += [p["io_l1_prefetch_req_valid"].eq(s3_valid),
                          p["io_l1_prefetch_req_bits_region"].eq(s3_l1_region),
                          p["io_l1_prefetch_req_bits_bit_vec"].eq(s3_l1_vector),
                          p["io_l2_l3_prefetch_req_valid"].eq(s4_valid),
                          p["io_l2_l3_prefetch_req_bits_region"].eq(s4_l2_region),
                          p["io_l2_l3_prefetch_req_bits_bit_vec"].eq(s4_l2_vector)]
        with cast(Any, module.If(s0_valid)):
            module.d.sync += replacement.eq(_plru_next(replacement, s0_index, 10))
        for i in range(10):
            alloc = s1_alloc & (s1_index == i)
            update = s1_update & (s1_index == i)
            delta_i = s1_vaddr[:16] - prev[i]
            block_delta_i = delta_i[6:16]
            valid_i = (delta_i != 0) & (delta_i != 1) & ~cast(Any, delta_i[15])
            match_i = delta_i == stride[i]
            with cast(Any, module.If(alloc)):
                module.d.sync += [valid[i].eq(1), prev[i].eq(s1_vaddr[:16]), stride[i].eq(0),
                                  confidence[i].eq(0), pc_hash[i].eq(s1_hash)]
            with cast(Any, module.If(update)):
                module.d.sync += prev[i].eq(s1_vaddr[:16])
                with cast(Any, module.If(valid_i & match_i & (confidence[i] != 3))):
                    module.d.sync += confidence[i].eq(confidence[i] + 1)
                with cast(Any, module.Elif(valid_i & ~match_i)):
                    module.d.sync += confidence[i].eq(Mux(confidence[i] == 0, 0, confidence[i] - 1))
                    with cast(Any, module.If(confidence[i] <= 1)):
                        module.d.sync += stride[i].eq(delta_i)
    # Elaborate. / 展开。
    def elaborate(self, platform: Any) -> Module:
        # Elaborate the selected stateful metadata array. / 展开选定的有状态元数据阵列。
        del platform
        module = Module()
        module.domains.sync = ClockDomain("sync", async_reset=True)
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
