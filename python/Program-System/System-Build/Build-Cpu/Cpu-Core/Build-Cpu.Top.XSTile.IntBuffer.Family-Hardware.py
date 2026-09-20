"""Source-backed IntBuffer family for the bounded XSTile closure.
锁定 XSTile 闭包的源代码 IntBuffer family。
"""
from __future__ import annotations

from typing import Any

from amaranth import ClockDomain, Elaboratable, Module, Signal
from amaranth.back import verilog

# Module Contract / 模块契约
__all__ = [
    'COVERED_MODULES',
    'PORT_SPECS',
    'FamilySpec',
    'IntBufferFamily',
    'TopXSTileIntBufferFamily',
    'family_spec',
    'build_verilog',
    'main',
]

# Configuration / 配置
COVERED_MODULES: tuple[str, ...] = ("IntBuffer", "IntBuffer_1", "IntBuffer_2")


PortSpec = tuple[str, str, int]

PORT_SPECS: dict[str, tuple[PortSpec, ...]] = {
    'IntBuffer': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('auto_in_0', 'input', 1),
        ('auto_out_0', 'output', 1),
    ),
    'IntBuffer_1': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('auto_in_0', 'input', 1),
        ('auto_in_1', 'input', 1),
        ('auto_out_0', 'output', 1),
        ('auto_out_1', 'output', 1),
    ),
    'IntBuffer_2': (
        ('clock', 'input', 1),
        ('reset', 'input', 1),
        ('auto_in_1_0', 'input', 1),
        ('auto_in_0_0', 'input', 1),
        ('auto_out_1_0', 'output', 1),
        ('auto_out_0_0', 'output', 1),
    ),
}








class FamilySpec:
    """Immutable locked-member view / 不可变的锁定成员视图。"""

    # Validate and capture one locked member / 校验并捕获一个锁定成员。
    def __init__(self, module: str) -> None:
        if module not in PORT_SPECS:
            raise ValueError(f"unknown IntBuffer member: {module}")
        self.module = module
        self.ports = PORT_SPECS[module]

    # Return the width of one named port / 返回指定端口的位宽。
    def width(self, name: str) -> int:
        for port_name, _direction, width in self.ports:
            if port_name == name:
                return width
        raise KeyError(name)


    # Resolve one family member specification / 解析一个 family 成员规格。
def family_spec(module: str) -> FamilySpec:
    return FamilySpec(module)


class IntBufferFamily(Elaboratable):
    """One exact resettable IntBuffer variant / 一个精确的可复位 IntBuffer 变体。"""

    # Allocate the exact locked ports and scalar registers / 分配精确锁定端口及标量寄存器。
    def __init__(self, module: str = COVERED_MODULES[0]) -> None:
        self.member = module
        self.spec = family_spec(module)
        self.ports: dict[str, Signal] = {
            name: Signal(width, name=name) for name, _direction, width in self.spec.ports
        }
        self.input_names = [name for name, _direction, _width in self.spec.ports if name.startswith("auto_in_")]
        self.output_names = [name for name, _direction, _width in self.spec.ports if name.startswith("auto_out_")]
        self.registers = [Signal(1, name=f"REG_{index}") for index in range(len(self.input_names))]

    # Elaborate the one-stage positive-reset register pipeline / 展开一级正复位寄存器流水线。
    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        domain = ClockDomain("sync", async_reset=True)
        domain.clk = self.ports["clock"]
        domain.rst = self.ports["reset"]
        module.domains += domain
        # Source IntBuffer uses RegNextN(..., depth=1, reset=0).  The emitted
        # reference has one ADFF per scalar lane and a direct output assignment.
        for register, input_name, output_name in zip(self.registers, self.input_names, self.output_names):
            module.d.sync += register.eq(self.ports[input_name])
            module.d.comb += self.ports[output_name].eq(register)
        return module


TopXSTileIntBufferFamily = IntBufferFamily


# Public Adapter / 公共适配器
# Export one deterministic selected member / 导出一个确定性的选定成员。
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    del injected_dependencies
    member = COVERED_MODULES[0]
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = IntBufferFamily(member)
    return verilog.convert(top, name=member, ports=[top.ports[name] for name, _direction, _width in top.spec.ports], emit_src=False)


# Emit the default member for direct invocation / 直接调用时输出默认成员。
def main() -> None:
    print(build_verilog({"module": COVERED_MODULES[0]}, {}))


# Direct Entry / 直接入口
if __name__ == "__main__":
    main()
