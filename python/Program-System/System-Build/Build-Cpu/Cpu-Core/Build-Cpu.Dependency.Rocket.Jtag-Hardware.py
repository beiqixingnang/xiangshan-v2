"""UHSC JTAG shifter family for the Kunminghu V2 snapshot.
昆明湖 V2 快照的 UHSC JTAG 移位链 family。

The five locked JtagShifter subjects are represented by one parameterized
aggregate.  The aggregate keeps the chain data path explicit and exposes the
same flattened ANSI names used by the pinned Rocket-Chip elaboration.
"""

from __future__ import annotations

from typing import Any, cast

from amaranth import Cat, ClockDomain, Elaboratable, Module, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
# The selected member names mirror the locked generated hierarchy. /
# 选定成员名称与锁定生成层级一致。
__all__ = ["COVERED_MODULES", "JtagShifterFamily", "build_verilog", "main"]

COVERED_MODULES: tuple[str, ...] = (
    "CaptureChain",
    "CaptureUpdateChain",
    "CaptureUpdateChain_1",
    "CaptureUpdateChain_2",
    "JtagBypassChain",
)

SOURCE_PATHS: tuple[str, ...] = (
    "upstream/rocket-chip/src/main/scala/jtag/JtagShifter.scala",
)

# Exact locked ports, in generated declaration order. / 锁定端口及生成声明顺序。
PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {
    "CaptureChain": (
        ("clock", "input", 1), ("reset", "input", 1),
        ("io_chainIn_shift", "input", 1), ("io_chainIn_data", "input", 1),
        ("io_chainIn_capture", "input", 1), ("io_chainIn_update", "input", 1),
        ("io_chainOut_data", "output", 1),
        ("io_capture_bits_version", "input", 4),
        ("io_capture_bits_partNumber", "input", 16),
        ("io_capture_bits_mfrId", "input", 11),
    ),
    "CaptureUpdateChain": (
        ("clock", "input", 1), ("reset", "input", 1),
        ("io_chainIn_shift", "input", 1), ("io_chainIn_data", "input", 1),
        ("io_chainIn_capture", "input", 1), ("io_chainIn_update", "input", 1),
        ("io_chainOut_data", "output", 1),
        ("io_capture_bits_dmiStatus", "input", 2),
        ("io_update_valid", "output", 1),
        ("io_update_bits_dmireset", "output", 1),
    ),
    "CaptureUpdateChain_1": (
        ("clock", "input", 1), ("reset", "input", 1),
        ("io_chainIn_shift", "input", 1), ("io_chainIn_data", "input", 1),
        ("io_chainIn_capture", "input", 1), ("io_chainIn_update", "input", 1),
        ("io_chainOut_data", "output", 1),
        ("io_capture_bits_addr", "input", 7),
        ("io_capture_bits_data", "input", 32),
        ("io_capture_bits_resp", "input", 2),
        ("io_capture_capture", "output", 1),
        ("io_update_valid", "output", 1),
        ("io_update_bits_addr", "output", 7),
        ("io_update_bits_data", "output", 32),
        ("io_update_bits_op", "output", 2),
    ),
    "CaptureUpdateChain_2": (
        ("clock", "input", 1), ("reset", "input", 1),
        ("io_chainIn_shift", "input", 1), ("io_chainIn_data", "input", 1),
        ("io_chainIn_capture", "input", 1), ("io_chainIn_update", "input", 1),
        ("io_chainOut_data", "output", 1),
        ("io_update_bits", "output", 5),
    ),
    "JtagBypassChain": (
        ("clock", "input", 1), ("reset", "input", 1),
        ("io_chainIn_shift", "input", 1), ("io_chainIn_data", "input", 1),
        ("io_chainIn_capture", "input", 1), ("io_chainIn_update", "input", 1),
        ("io_chainOut_data", "output", 1),
    ),
}


# =============================================================================
# Configuration
# =============================================================================
def capture_width(member: str) -> int:
    """Return the parallel capture width. / 返回并行捕获位宽。"""

    if member == "CaptureChain":
        return 32
    if member == "CaptureUpdateChain":
        return 32
    if member == "CaptureUpdateChain_1":
        return 41
    if member == "CaptureUpdateChain_2":
        return 5
    return 1


def update_width(member: str) -> int:
    """Return the parallel update width. / 返回并行更新位宽。"""

    if member == "CaptureUpdateChain":
        return 32
    if member == "CaptureUpdateChain_1":
        return 41
    if member == "CaptureUpdateChain_2":
        return 5
    return 1


def chain_width(member: str) -> int:
    """Return the register width used by one member. / 返回成员移位寄存器位宽。"""

    return max(capture_width(member), update_width(member))


# =============================================================================
# Implementation
# =============================================================================
class JtagShifterFamily(Elaboratable):
    """One exact JTAG shifter member selected by ``member``. / 由 member 选择的精确 JTAG 移位成员。"""

    def __init__(self, member: str = "JtagBypassChain") -> None:
        """Declare the locked flattened ports. / 声明锁定的扁平端口。"""

        if member not in PORT_SPECS:
            raise ValueError(f"unsupported JTAG member: {member}")
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports: dict[str, Signal] = {
            name: Signal(width, name=name)
            for name, _direction, width in self.specs
        }
        self.clock = self.ports["clock"]
        self.reset = self.ports["reset"]

    # Return a declared signal by locked name. / 按锁定名称返回信号。
    def port(self, name: str) -> Signal:
        """Look up one flattened port. / 查找一个扁平端口。"""

        return self.ports[name]

    # Assign parallel capture payload into the low-to-high register bits. /
    # 将并行捕获载荷按低位到高位写入寄存器。
    def capture_payload(self) -> Any:
        """Return the packed capture payload. / 返回打包的捕获载荷。"""

        if self.member == "CaptureChain":
            return 1 | (self.port("io_capture_bits_mfrId") << 1) | (
                self.port("io_capture_bits_partNumber") << 12
            ) | (self.port("io_capture_bits_version") << 28)
        if self.member == "CaptureUpdateChain":
            return 0x5071 | (self.port("io_capture_bits_dmiStatus") << 10)
        if self.member == "CaptureUpdateChain_1":
            return self.port("io_capture_bits_resp") | (
                self.port("io_capture_bits_data") << 2
            ) | (self.port("io_capture_bits_addr") << 34)
        if self.member == "CaptureUpdateChain_2":
            return 1
        return 0

    # Drive update outputs from the register payload. / 用寄存器载荷驱动更新输出。
    def drive_update_outputs(self, module: Module, registers: list[Signal]) -> None:
        """Connect member-specific update fields. / 连接成员专用更新字段。"""

        if self.member == "CaptureUpdateChain":
            module.d.comb += self.port("io_update_bits_dmireset").eq(registers[16])
        elif self.member == "CaptureUpdateChain_1":
            module.d.comb += [
                self.port("io_update_bits_addr").eq(Cat(*registers[34:41])),
                self.port("io_update_bits_data").eq(Cat(*registers[2:34])),
                self.port("io_update_bits_op").eq(Cat(*registers[0:2])),
            ]
        elif self.member == "CaptureUpdateChain_2":
            module.d.comb += self.port("io_update_bits").eq(Cat(*registers))

    # Build the selected shifter's sequential and combinational behavior. /
    # 构建选定移位器的时序与组合行为。
    def elaborate(self, platform: Any) -> Module:
        """Elaborate one locked JTAG member. / 展开一个锁定 JTAG 成员。"""

        del platform
        module = Module()
        domain = ClockDomain("sync", reset_less=True)
        domain.clk = self.clock
        module.domains += domain

        width = chain_width(self.member)
        registers = [
            Signal(name=f"regs_{index}", reset_less=True)
            for index in range(width)
        ]
        module.d.comb += self.port("io_chainOut_data").eq(registers[0])

        # Outputs absent from a member's locked surface are intentionally not
        # created; every exposed update/capture flag has an explicit default.
        # 锁定表面中不存在的输出不创建；所有公开标志都有明确默认值。
        if "io_update_valid" in self.ports:
            module.d.comb += self.port("io_update_valid").eq(
                ~self.port("io_chainIn_capture") & self.port("io_chainIn_update")
            )
        if "io_capture_capture" in self.ports:
            module.d.comb += self.port("io_capture_capture").eq(
                self.port("io_chainIn_capture")
            )
        self.drive_update_outputs(module, registers)

        # Capture has priority over shift, matching the Chisel when/elsewhen
        # chain.  Update is a pulse-only observation and does not alter state.
        # 捕获优先于移位，与 Chisel when/elsewhen 链一致；更新只产生脉冲。
        capture = self.port("io_chainIn_capture")
        shift = self.port("io_chainIn_shift")
        with cast(Any, module.If(capture)):
            payload = self.capture_payload()
            for index, register in enumerate(registers):
                module.d.sync += register.eq((payload >> index) & 1)
        update_suppresses_shift = self.member.startswith("CaptureUpdateChain")
        shift_enabled = shift & ~self.port("io_chainIn_update") if update_suppresses_shift else shift
        with cast(Any, module.Elif(shift_enabled)):
            for index in range(width - 1):
                module.d.sync += registers[index].eq(registers[index + 1])
            module.d.sync += registers[-1].eq(self.port("io_chainIn_data"))
        return module


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: Any, injected_dependencies: Any) -> str:
    """Export one deterministic same-name JTAG member. / 导出确定性的同名 JTAG 成员。"""

    del injected_dependencies
    member = "JtagBypassChain"
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = JtagShifterFamily(member)
    ports = [top.ports[name] for name, _direction, _width in top.specs]
    return verilog.convert(top, name=member, ports=ports, emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    """Print the default bypass-chain Verilog. / 打印默认旁路链 Verilog。"""

    print(build_verilog({"module": "JtagBypassChain"}, {}))


if __name__ == "__main__":
    main()
