"""V2 NewCSR PMP and PMA entry handlers: address state, lock rules and read masks. / V2 NewCSR 的 PMP 与 PMA 条目处理器：地址状态、锁定规则与读掩码。"""

from __future__ import annotations

from typing import Any, cast

from amaranth import Cat, ClockDomain, Const, Elaboratable, Module, Mux, Signal

# =============================================================================
# Module Contract
# =============================================================================
# Scope of this aggregate subject.  The locked hierarchy holds 396 modules whose
# Scala provenance is `xiangshan/backend/fu/NewCSR/`.  The sibling subject
# `Build-Cpu.Backend.Fu.NewCSR.CSRModule-Hardware.py` already emits 374 of them
# and this file adds the two PMP/PMA entry handlers, so 20 NewCSR modules stay
# with other subjects (permit, trigger, trap and interrupt modules).  This file is
# therefore exactly `PMPEntryHandleModule` and `PMAEntryHandleModule`
# (`PMPEntryModule.scala`, `PMAEntryModule.scala`), plus the CSR address indices
# they decode.  No other module is restated here.
#
# Faithfulness rules taken from the pinned artifact `build/rtl/XSTop.sv`
# (sha256 8f279a52...), module bodies `PMPEntryHandleModule` and
# `PMAEntryHandleModule`:
#  * Ports: name, direction and width are the locked ANSI list, verbatim.
#  * Address state: one `PMPAddrBits`-wide register per entry, asynchronous
#    reset, `io_in_wdata[45:0]` on write.
#  * Lock rule: `addrLocked(i) = L(i) | (L(i+1) & A(i+1) == TOR)`; the last
#    entry has no successor and uses `L(i)` alone.
#  * Write-back word: each packed `Pmpcfg*`/`Pmacfg*` word is eight eight-bit
#    entry images, MSB entry last, each image only present while its own word
#    strobe is active, and per field `L ? held : wdata`.
#  * Read data: `{18'h0, ren & addr_hit ? masked(addr) : addr}` with the
#    platform-grain mask `{addr[45:9], 9'h1FF}` for NAPOT and
#    `{addr[45:10], 10'h0}` otherwise.
#  * PMA entries additionally reset to `PMA_ENTRY_RESET_ADDRESSES`.
# 本聚合主体的范围。锁定层级中 Scala 出处位于 `xiangshan/backend/fu/NewCSR/` 的模块共
# 396 个；同批主体 `Build-Cpu.Backend.Fu.NewCSR.CSRModule-Hardware.py` 已输出其中 374 个，
# 本文件补上 PMP、PMA 两个条目处理器，另有 20 个 NewCSR 模块归其它主体（permit、trigger、
# trap、中断等）。因此本文件恰好实现 `PMPEntryHandleModule` 与 `PMAEntryHandleModule`
# （PMPEntryModule.scala、PMAEntryModule.scala）及其解码的 CSR 地址索引，不复述其它模块。
# 忠实性规则取自锁定产物 `build/rtl/XSTop.sv` 的两个模块体：端口逐字照抄；每条目
# 一个 `PMPAddrBits` 宽地址寄存器、异步复位、写入 `io_in_wdata[45:0]`；锁定规则
# `L(i) | (L(i+1) & A(i+1)==TOR)`；写回字为八个 8 位条目映像、高位条目在后、仅在本字
# 选通时出现、逐字段 `L ? 保持 : wdata`；读回 `{18'h0, ren&命中 ? 粒度掩码 : addr}`；
# PMA 条目另有复位初值。
__all__ = [
    "XLEN",
    "PMP_ADDR_BITS",
    "PMP_OFF_BITS",
    "PLATFORM_GRAIN",
    "NUM_PMP_REAL",
    "NUM_PMA_REAL",
    "PMP_CFG_BASE",
    "PMP_CFG_REGISTER_STRIDE",
    "PMP_CFG_ENTRY_BASES",
    "PMP_ADDR_BASE",
    "PMA_CFG_BASE",
    "PMA_ADDR_BASE",
    "PMP_CFG_WORD_ADDRESSES",
    "PMP_ENTRY_ADDRESSES",
    "PMA_CFG_WORD_ADDRESSES",
    "PMA_ENTRY_ADDRESSES",
    "PMA_ENTRY_RESET_ADDRESSES",
    "HANDLER_MODULE_NAMES",
    "COVERED_MODULES",
    "SOURCE_PATHS",
    "pmp_word_images",
    "pma_word_images",
    "cfg_word_selected",
    "clock_domain",
    "grain_masked",
    "PmpEntryHandleModule",
    "PmaEntryHandleModule",
    "emitted_module_names",
    "handler_ports",
    "build_verilog",
    "main",
]


# =============================================================================
# Configuration
# =============================================================================
# Architectural constants of the locked artifact and of the V2 parameters
# `XLen`, `PMPAddrBits`, `PMPOffBits`, `PlatformGrain`, `NumPMPReal`,
# `NumPMAReal`. / 锁定产物与 V2 参数中的架构常量。
XLEN = 64
PMP_ADDR_BITS = 46
PMP_OFF_BITS = 2
PLATFORM_GRAIN = 12
NUM_PMP_REAL = 32
NUM_PMA_REAL = 32

# CSR address indices decoded by the two handlers: `CSRs.pmpcfg0` /
# `CSRConst.PmacfgBase` for the four real packed configuration words and
# `CSRs.pmpaddr0` / `CSRConst.PmaaddrBase` for the per-entry address registers.
# 两个处理器解码的 CSR 地址索引：四个实际配置字用 pmpcfg0/PmacfgBase，逐条目地址
# 寄存器用 pmpaddr0/PmaaddrBase。
PMP_CFG_BASE = 0x3A0
PMP_CFG_REGISTER_STRIDE = 2
PMP_ADDR_BASE = 0x3B0
PMA_CFG_BASE = 0x7C0
PMA_ADDR_BASE = 0x7C8
PMP_CFG_WORD_ADDRESSES = tuple(
    PMP_CFG_BASE + PMP_CFG_REGISTER_STRIDE * word for word in range(4)
)
PMP_ENTRY_ADDRESSES = tuple(PMP_ADDR_BASE + index for index in range(NUM_PMP_REAL))
PMA_CFG_WORD_ADDRESSES = tuple(
    PMA_CFG_BASE + PMP_CFG_REGISTER_STRIDE * word for word in range(4)
)
PMA_ENTRY_ADDRESSES = tuple(PMA_ADDR_BASE + index for index in range(NUM_PMA_REAL))
# Each packed word holds eight entry images, entry `base + offset` at byte
# `offset`. / 每个打包字含 8 个条目映像，条目 base+offset 位于第 offset 字节。
PMP_CFG_ENTRY_BASES = (0, 8, 16, 24)

# Address-register reset values of `PMAEntryHandleModule`, read from the reset
# block of the locked artifact. / PMAEntryHandleModule 地址寄存器复位值，取自工件复位块。
PMA_ENTRY_RESET_ADDRESSES = (
        0x0,
    0x0,
    0x0,
    0x0,
    0x0,
    0x0,
    0x0,
    0x0,
    0x0,
    0x0,
    0x0,
    0x0,
    0x0,
    0x0,
    0x0,
    0x0,
    0x0,
    0x0,
    0x0,
    0x4000000,
    0x8000000,
    0xC004000,
    0xC014000,
    0xE008000,
    0xE008400,
    0xE008800,
    0xE400000,
    0xE400800,
    0xE800000,
    0x20000000,
    0x20000000000,
    0x1FFFFFFFFFFF,
)

# The two locked module names this subject implements. / 本主体实现的锁定模块名。
HANDLER_MODULE_NAMES: tuple[str, ...] = ("PMPEntryHandleModule", "PMAEntryHandleModule")
COVERED_MODULES: tuple[str, ...] = HANDLER_MODULE_NAMES
SOURCE_PATHS: tuple[str, ...] = (
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/PMPEntryModule.scala",
    "upstream/src/main/scala/xiangshan/backend/fu/NewCSR/PMAEntryModule.scala",
)


# =============================================================================
# Implementation
# =============================================================================
# Pack the eight WARL entry images of one selected `Pmpcfg*` word. / 打包被选中 Pmpcfg* 字的八个 WARL 条目映像。
def pmp_word_images(entries: list[dict[str, Any]], entry_base: int, wdata: Any) -> Any:
    """Return one `Pmpcfg*` word image. / 返回一个 Pmpcfg* 字映像。"""

    images = []
    for offset in range(8):
        entry = entries[entry_base + offset]
        base = 8 * offset
        images.append(Cat(
            Mux(entry["L"], entry["R"], wdata[base + 0]),
            Mux(entry["L"], entry["W"], wdata[base + 1] & wdata[base + 0]),
            Mux(entry["L"], entry["X"], wdata[base + 2]),
            Mux(entry["L"], entry["A"],
                Cat(wdata[base + 4] | wdata[base + 3], wdata[base + 4])),
            (~entry["L"]) & wdata[base + 5],
            (~entry["L"]) & wdata[base + 6],
            Mux(entry["L"], entry["L"], wdata[base + 7]),
        ))
    return Cat(*images)


# Pack the eight WARL entry images of one selected `Pmacfg*` word. / 打包被选中 Pmacfg* 字的八个 WARL 条目映像。
def pma_word_images(entries: list[dict[str, Any]], entry_base: int, wdata: Any) -> Any:
    """Return one `Pmacfg*` word image. / 返回一个 Pmacfg* 字映像。"""

    images = []
    for offset in range(8):
        entry = entries[entry_base + offset]
        base = 8 * offset
        images.append(Cat(
            Mux(entry["L"], entry["R"], wdata[base + 0]),
            Mux(entry["L"], entry["W"], wdata[base + 1] & wdata[base + 0]),
            Mux(entry["L"], entry["X"], wdata[base + 2]),
            Mux(entry["L"], entry["A"],
                Cat(wdata[base + 4] | wdata[base + 3], wdata[base + 4])),
            Mux(entry["L"], entry["ATOMIC"], wdata[base + 5]),
            Mux(entry["L"], entry["C"], wdata[base + 6]),
            Mux(entry["L"], entry["L"], wdata[base + 7]),
        ))
    return Cat(*images)


# Select the write-back word with the artifact's four-level strobe nesting.
# 按工件的四级选通嵌套选择写回字。
def cfg_word_selected(selected: list[Any], images: list[Any]) -> Any:
    """Return `sel3 ? img3 : sel2 ? img2 : sel1 ? img1 : sel0 & img0`. / 返回工件四级选通嵌套的结果。"""

    result: Any = images[0] & selected[0].replicate(XLEN)
    for index in range(1, len(images)):
        result = Mux(selected[index], images[index], result)
    return result


# Create the asynchronous-reset clock domain used by both handlers.
# 创建两个处理器共用的异步复位时钟域。
def clock_domain(clock: Any, reset: Any) -> ClockDomain:
    """Return the `sync` domain bound to the module clock and reset. / 返回绑定模块时钟与复位的 sync 时钟域。"""

    domain = ClockDomain("sync", async_reset=True)
    domain.clk = clock
    domain.rst = reset
    return domain


# Apply the V2 platform-grain mask to one entry address read. / 对单个条目地址读回施加 V2 平台粒度掩码。
def grain_masked(address: Any, napot: Any) -> Any:
    """Return `{addr[45:9], 9'h1FF}` for NAPOT and `{addr[45:10], 10'h0}` otherwise. / 返回 NAPOT 下的 9 位置一掩码，否则清 10 位。"""

    low = PLATFORM_GRAIN - PMP_OFF_BITS
    return Mux(napot,
               Cat(Const((1 << (low - 1)) - 1, low - 1), address[low - 1:PMP_ADDR_BITS]),
               Cat(Const(0, low), address[low:PMP_ADDR_BITS]))


# Reproduce `PMPEntryHandleModule`: address state, lock rule and read masks.
# 复现 `PMPEntryHandleModule`：地址状态、锁定规则与读掩码。
class PmpEntryHandleModule(Elaboratable):
    """Implement the locked V2 PMP entry handler. / 实现锁定的 V2 PMP 条目处理器。"""

    # Declare the 199 locked ports of `PMPEntryHandleModule`. / 声明 PMPEntryHandleModule 的 199 个锁定端口。
    def __init__(self) -> None:
        """Create the clocked PMP entry handler ports. / 创建时钟化 PMP 条目处理器端口。"""

        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.io_in_wen = Signal(name="io_in_wen")
        self.io_in_ren = Signal(name="io_in_ren")
        self.io_in_addr = Signal(12, name="io_in_addr")
        self.io_in_wdata = Signal(XLEN, name="io_in_wdata")
        self.pmp_cfg: list[dict[str, Any]] = []
        for index in range(NUM_PMP_REAL):
            self.pmp_cfg.append({
                "R": Signal(name=f"io_in_pmpCfg_{index}_R"),
                "W": Signal(name=f"io_in_pmpCfg_{index}_W"),
                "X": Signal(name=f"io_in_pmpCfg_{index}_X"),
                "A": Signal(2, name=f"io_in_pmpCfg_{index}_A"),
                "L": Signal(name=f"io_in_pmpCfg_{index}_L"),
            })
        self.io_out_pmpCfgWData = Signal(XLEN, name="io_out_pmpCfgWData")
        self.io_out_pmpAddrRData = [
            Signal(XLEN, name=f"io_out_pmpAddrRData_{index}") for index in range(NUM_PMP_REAL)
        ]

    # Elaborate the address registers, the lock qualification and the read data.
    # 展开地址寄存器、锁定资格与读数据。
    def elaborate(self, platform: Any) -> Module:
        """Return the PMP entry handler. / 返回 PMP 条目处理器模块。"""

        del platform
        module = Module()
        module.domains += clock_domain(self.clock, self.reset)
        addresses = [
            Signal(PMP_ADDR_BITS, name=f"pmpAddr_{index}_ADDRESS", reset=0)
            for index in range(NUM_PMP_REAL)
        ]
        for index, address in enumerate(addresses):
            if index != NUM_PMP_REAL - 1:
                successor = self.pmp_cfg[index + 1]
                locked = self.pmp_cfg[index]["L"] | (successor["L"] & (successor["A"] == 1))
            else:
                locked = self.pmp_cfg[index]["L"]
            with cast(Any, module.If(self.io_in_wen
                                     & (self.io_in_addr == PMP_ENTRY_ADDRESSES[index])
                                     & ~locked)):
                module.d.sync += address.eq(self.io_in_wdata[0:PMP_ADDR_BITS])
        for index, address in enumerate(addresses):
            module.d.comb += self.io_out_pmpAddrRData[index].eq(
                Cat(Mux(self.io_in_ren & (self.io_in_addr == PMP_ENTRY_ADDRESSES[index]),
                        grain_masked(address, self.pmp_cfg[index]["A"][1]), address),
                    Const(0, XLEN - PMP_ADDR_BITS)))
        module.d.comb += self.io_out_pmpCfgWData.eq(
            self.cfg_write_back(self.io_in_wdata))
        return module

    # Build the packed configuration write-back word of the selected `Pmpcfg*`.
    # 构建被选中的 `Pmpcfg*` 打包配置写回字。
    def cfg_write_back(self, wdata: Any) -> Any:
        """Return the 64-bit WARL write-back image. / 返回 64 位 WARL 写回映像。"""

        return cfg_word_selected(
            [self.io_in_wen & (self.io_in_addr == address)
             for address in PMP_CFG_WORD_ADDRESSES],
            [pmp_word_images(self.pmp_cfg, entry_base, wdata)
             for entry_base in PMP_CFG_ENTRY_BASES])

    # Report the locked port signals in their declared order. / 按声明顺序报告锁定端口信号。
    def top_ports(self) -> list[Any]:
        """Return the ordered `PMPEntryHandleModule` port signals. / 返回有序的 PMPEntryHandleModule 端口信号。"""

        ports: list[Any] = [self.clock, self.reset, self.io_in_wen, self.io_in_ren,
                            self.io_in_addr, self.io_in_wdata]
        for entry in self.pmp_cfg:
            ports.extend([entry["R"], entry["W"], entry["X"], entry["A"], entry["L"]])
        ports.append(self.io_out_pmpCfgWData)
        ports.extend(self.io_out_pmpAddrRData)
        return ports


# Reproduce `PMAEntryHandleModule`: the same control with ATOMIC/C fields and
# initialised address entries. / 复现 `PMAEntryHandleModule`：控制相同，另有 ATOMIC/C 字段与地址初值。
class PmaEntryHandleModule(Elaboratable):
    """Implement the locked V2 PMA entry handler. / 实现锁定的 V2 PMA 条目处理器。"""

    # Declare the 263 locked ports of `PMAEntryHandleModule`. / 声明 PMAEntryHandleModule 的 263 个锁定端口。
    def __init__(self) -> None:
        """Create the clocked PMA entry handler ports. / 创建时钟化 PMA 条目处理器端口。"""

        self.clock = Signal(name="clock")
        self.reset = Signal(name="reset")
        self.io_in_wen = Signal(name="io_in_wen")
        self.io_in_ren = Signal(name="io_in_ren")
        self.io_in_addr = Signal(12, name="io_in_addr")
        self.io_in_wdata = Signal(XLEN, name="io_in_wdata")
        self.pma_cfg: list[dict[str, Any]] = []
        for index in range(NUM_PMA_REAL):
            self.pma_cfg.append({
                "R": Signal(name=f"io_in_pmaCfg_{index}_R"),
                "W": Signal(name=f"io_in_pmaCfg_{index}_W"),
                "X": Signal(name=f"io_in_pmaCfg_{index}_X"),
                "A": Signal(2, name=f"io_in_pmaCfg_{index}_A"),
                "L": Signal(name=f"io_in_pmaCfg_{index}_L"),
                "ATOMIC": Signal(name=f"io_in_pmaCfg_{index}_ATOMIC"),
                "C": Signal(name=f"io_in_pmaCfg_{index}_C"),
            })
        self.io_out_pmaCfgWdata = Signal(XLEN, name="io_out_pmaCfgWdata")
        self.io_out_pmaAddrRData = [
            Signal(XLEN, name=f"io_out_pmaAddrRData_{index}") for index in range(NUM_PMA_REAL)
        ]

    # Elaborate the initialised address registers, lock qualification and reads.
    # 展开带初值的地址寄存器、锁定资格与读数据。
    def elaborate(self, platform: Any) -> Module:
        """Return the PMA entry handler. / 返回 PMA 条目处理器模块。"""

        del platform
        module = Module()
        module.domains += clock_domain(self.clock, self.reset)
        addresses = [
            Signal(PMP_ADDR_BITS, name=f"pmaAddr_{index}",
                   reset=PMA_ENTRY_RESET_ADDRESSES[index])
            for index in range(NUM_PMA_REAL)
        ]
        for index, address in enumerate(addresses):
            if index != NUM_PMA_REAL - 1:
                successor = self.pma_cfg[index + 1]
                locked = self.pma_cfg[index]["L"] | (successor["L"] & (successor["A"] == 1))
            else:
                locked = self.pma_cfg[index]["L"]
            with cast(Any, module.If(self.io_in_wen
                                     & (self.io_in_addr == PMA_ENTRY_ADDRESSES[index])
                                     & ~locked)):
                module.d.sync += address.eq(self.io_in_wdata[0:PMP_ADDR_BITS])
        for index, address in enumerate(addresses):
            module.d.comb += self.io_out_pmaAddrRData[index].eq(
                Cat(Mux(self.io_in_ren & (self.io_in_addr == PMA_ENTRY_ADDRESSES[index]),
                        grain_masked(address, self.pma_cfg[index]["A"][1]), address),
                    Const(0, XLEN - PMP_ADDR_BITS)))
        module.d.comb += self.io_out_pmaCfgWdata.eq(
            self.cfg_write_back(self.io_in_wdata))
        return module

    # Build the packed configuration write-back word of the selected `Pmacfg*`.
    # 构建被选中的 `Pmacfg*` 打包配置写回字。
    def cfg_write_back(self, wdata: Any) -> Any:
        """Return the 64-bit WARL write-back image. / 返回 64 位 WARL 写回映像。"""

        return cfg_word_selected(
            [self.io_in_wen & (self.io_in_addr == address)
             for address in PMA_CFG_WORD_ADDRESSES],
            [pma_word_images(self.pma_cfg, entry_base, wdata)
             for entry_base in PMP_CFG_ENTRY_BASES])

    # Report the locked port signals in their declared order. / 按声明顺序报告锁定端口信号。
    def top_ports(self) -> list[Any]:
        """Return the ordered `PMAEntryHandleModule` port signals. / 返回有序的 PMAEntryHandleModule 端口信号。"""

        ports: list[Any] = [self.clock, self.reset, self.io_in_wen, self.io_in_ren,
                            self.io_in_addr, self.io_in_wdata]
        for entry in self.pma_cfg:
            ports.extend([entry["R"], entry["W"], entry["X"], entry["A"], entry["L"],
                          entry["ATOMIC"], entry["C"]])
        ports.append(self.io_out_pmaCfgWdata)
        ports.extend(self.io_out_pmaAddrRData)
        return ports


# Instantiate one handler by its locked module name. / 按锁定模块名实例化一个处理器。
def handler_ports(name: str) -> tuple[Elaboratable, list[Any]]:
    """Return the handler instance and its ordered ports. / 返回处理器实例与其有序端口。"""

    if name == "PMPEntryHandleModule":
        handler = PmpEntryHandleModule()
    elif name == "PMAEntryHandleModule":
        handler = PmaEntryHandleModule()
    else:
        raise KeyError(name)
    return handler, handler.top_ports()


# =============================================================================
# Public Adapter
# =============================================================================
# List the modules this subject emits, in a fixed deterministic order.
# 按固定确定性顺序列出本主体输出的模块。
def emitted_module_names() -> list[str]:
    """Return the emitted module names. / 返回输出的模块名。"""

    return list(HANDLER_MODULE_NAMES)


# Emit one handler as Verilog under its locked module name. / 以锁定模块名把一个处理器输出为 Verilog。
def handler_verilog(name: str) -> str:
    """Return the deterministic Verilog text of one handler. / 返回单个处理器的确定性 Verilog 文本。"""

    from amaranth.back import verilog

    handler, ports = handler_ports(name)
    return verilog.convert(handler, name=name, ports=ports, emit_src=False)


# Resolve the adapter configuration into the emitted module selection.
# 将适配器配置解析为待输出模块选择。
def emitted_selection(configuration: Any, injected_dependencies: Any) -> tuple[str, ...]:
    """Return the module names selected by the adapter configuration. / 返回适配器配置选中的模块名。"""

    del injected_dependencies
    if configuration is None:
        return tuple(HANDLER_MODULE_NAMES)
    if isinstance(configuration, str):
        return (configuration,)
    if isinstance(configuration, dict):
        selected = configuration.get("module", configuration.get("name"))
        if selected is not None:
            return (str(selected),)
        listed = configuration.get("modules")
        if listed is not None:
            return tuple(str(item) for item in listed)
    return tuple(HANDLER_MODULE_NAMES)


# Emit deterministic Verilog for the whole CSR level handler family.
# 为整个 CSR 层级处理器族输出确定性 Verilog。
def build_verilog(configuration: Any = None,
                  injected_dependencies: dict[str, Any] | None = None) -> str:
    """Build the family adapter and return the generated Verilog. / 构建族适配器并返回生成的 Verilog。"""

    selection = emitted_selection(configuration, injected_dependencies)
    for name in selection:
        if name not in HANDLER_MODULE_NAMES:
            raise KeyError(f"{name} is outside this subject's covered set")
    banner = "// CSR_LEVEL_HANDLER_FAMILY covered={} requested={} source=XSTop.sv\n".format(
        len(HANDLER_MODULE_NAMES), len(selection))
    return banner + "\n".join(handler_verilog(name) for name in selection)


# =============================================================================
# Direct Entry
# =============================================================================
# Print the generated family Verilog. / 打印生成的族 Verilog。
def main() -> None:
    """Print deterministic Verilog output. / 打印确定性 Verilog 输出。"""

    print(build_verilog(None, {}))


if __name__ == "__main__":
    main()
