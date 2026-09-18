"""Source-backed V2 ROB/rename/trace aggregate with locked ANSI ports.

该聚合主体覆盖 ExceptionGen、DiffRatStateBuffer 及其 SRAM/tag 叶子、
RenameBuffer/SnapshotGenerator、CompressUnit 与 Trace/TraceBuffer。端口表只
来自冻结的 ``v2-locked-hierarchy.json``；实现保持有界、确定性并为后续完整
父级差分保留明确边界。所有目标通过一个 Build 文件选择，避免把一个 Scala
源机械复制成多个 Python 文件。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from amaranth import Array, ClockDomain, Const, Elaboratable, Mux, Module, Signal
from amaranth.back import verilog

__all__ = [
    "COVERED_MODULES",
    "SOURCE_PATHS",
    "LOCKED_REFERENCE_SHA256",
    "PORT_SPECS",
    "RobRenameTraceFamily",
    "build_verilog",
    "main",
]

COVERED_MODULES = (
    "ExceptionGen",
    "DiffRatStateBuffer",
    "diff_rat_state_bank_320x776",
    "stateBankTags_320x3",
    "RenameBuffer",
    "SnapshotGenerator",
    "CompressUnit",
    "Trace",
    "TraceBuffer",
)
SOURCE_PATHS = (
    "upstream/src/main/scala/xiangshan/backend/rob/ExceptionGen.scala",
    "upstream/src/main/scala/xiangshan/backend/rob/DiffRatStateBuffer.scala",
    "upstream/src/main/scala/xiangshan/backend/rob/Rab.scala",
    "upstream/src/main/scala/xiangshan/backend/rename/CompressUnit.scala",
    "upstream/src/main/scala/xiangshan/backend/rename/Snapshot.scala",
    "upstream/src/main/scala/xiangshan/backend/trace/Trace.scala",
    "upstream/src/main/scala/xiangshan/backend/trace/TraceBuffer.scala",
)
LOCKED_REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"


def _repo_root() -> Path:
    """Return the V2 auxiliary repository root. / 返回 V2 辅助仓库根目录。"""

    return Path(__file__).resolve().parents[5]


def _width(value: Any) -> int:
    """Convert a frozen Verilog range into a bit width. / 转换冻结位宽。"""

    text = str(value or "").strip()
    if not text:
        return 1
    if text.startswith("[") and text.endswith("]") and ":" in text:
        high, low = text[1:-1].split(":", 1)
        return abs(int(high) - int(low)) + 1
    return 1


def _load_locked_ports() -> dict[str, tuple[tuple[str, str, int], ...]]:
    """Load exact port order/direction/width from the pinned hierarchy."""

    payload = json.loads(
        (_repo_root() / "validation" / "v2-locked-hierarchy.json").read_text(
            encoding="utf-8"
        )
    )
    if payload.get("reference_sha256") != LOCKED_REFERENCE_SHA256:
        raise RuntimeError("locked XSTop hierarchy digest changed")
    modules = payload.get("modules", {})
    result: dict[str, tuple[tuple[str, str, int], ...]] = {}
    for name in COVERED_MODULES:
        entry = modules.get(name)
        if not isinstance(entry, dict) or not isinstance(entry.get("ports"), list):
            raise KeyError(f"missing locked module {name}")
        result[name] = tuple(
            (str(port["name"]), str(port["direction"]), _width(port.get("width")))
            for port in entry["ports"]
        )
    return result


PORT_SPECS = _load_locked_ports()


def _or(values: list[Any]) -> Any:
    """OR a list of Amaranth values without an empty reduction."""

    if not values:
        return Const(0)
    value = values[0]
    for item in values[1:]:
        value = value | item
    return value


class _LockedMember(Elaboratable):
    """One member with the frozen ANSI surface and bounded semantics."""

    def __init__(self, member: str) -> None:
        if member not in PORT_SPECS:
            raise ValueError(f"unknown member: {member}")
        self.member = member
        self.specs = PORT_SPECS[member]
        self.ports = {name: Signal(width, name=name) for name, _d, width in self.specs}
        self.all_ports = [self.ports[name] for name, _d, _w in self.specs]

    def _domain(self, module: Module) -> None:
        """Connect a deterministic synchronous domain when present."""

        if "clock" in self.ports:
            domain = ClockDomain("sync", async_reset="reset" in self.ports)
            domain.clk = self.ports["clock"]
            if "reset" in self.ports:
                domain.rst = self.ports["reset"]
            module.domains.sync = domain

    def _defaults(self, module: Module, assigned: set[str]) -> None:
        """Drive every unhandled output to a known zero."""

        for name, direction, width in self.specs:
            if direction == "output" and name not in assigned:
                module.d.comb += self.ports[name].eq(Const(0, width))

    def _compress(self, module: Module, assigned: set[str]) -> None:
        """Implement the Scala contiguous ROB-compression lookup table."""

        width = 6
        can: list[Any] = []
        for index in range(width):
            valid = self.ports[f"io_in_{index}_valid"]
            exc = _or([self.ports[f"io_in_{index}_bits_exceptionVec_{j}"] for j in range(24)])
            trigger = self.ports[f"io_in_{index}_bits_trigger"]
            fused = self.ports[f"io_in_{index}_bits_commitType"] == 7
            can.append(valid & self.ports[f"io_in_{index}_bits_canRobCompress"] &
                       self.ports[f"io_in_{index}_bits_lastUop"] & ~exc & ~trigger.any() & ~fused)
        key = sum((can[i] << i) for i in range(width))
        # Build the exact generation-time table used by CompressUnit.scala.
        need_table: list[list[int]] = []
        size_table: list[list[int]] = []
        mask_table: list[list[int]] = []
        for candidate in range(1 << width):
            bits = [0] + [(candidate >> i) & 1 for i in range(width)] + [0]
            left = []
            right = []
            for i in range(1, width + 1):
                n = 0
                j = i
                while bits[j]:
                    n += 1
                    j -= 1
                left.append(n)
                n = 0
                j = i
                while bits[j]:
                    n += 1
                    j += 1
                right.append(n)
            sizes = [1 if not bits[i + 1] else left[i] + right[i] - 1 for i in range(width)]
            needs = [int(not (bits[i + 1] and bits[i + 2])) for i in range(width)]
            masks = []
            for i, size in enumerate(sizes):
                if not bits[i + 1]:
                    masks.append(1 << i)
                else:
                    start = i - left[i] + 1
                    masks.append(((1 << size) - 1) << start)
            need_table.append(needs)
            size_table.append(sizes)
            mask_table.append(masks)
        need_rom = Array(Const(sum(v << i for i, v in enumerate(row)), width) for row in need_table)
        size_rom = [Array(Const(row[i], 3) for row in size_table) for i in range(width)]
        mask_rom = [Array(Const(row[i], width) for row in mask_table) for i in range(width)]
        for i in range(width):
            self._eq(module, f"io_out_needRobFlags_{i}", need_rom[key][i])
            self._eq(module, f"io_out_instrSizes_{i}", size_rom[i][key])
            self._eq(module, f"io_out_masks_{i}", mask_rom[i][key])
            self._eq(module, f"io_out_canCompressVec_{i}", can[i])
            assigned.update({f"io_out_needRobFlags_{i}", f"io_out_instrSizes_{i}",
                             f"io_out_masks_{i}", f"io_out_canCompressVec_{i}"})

    def _diffrat(self, module: Module, assigned: set[str]) -> None:
        """Forward base RAT through six rename lanes (bounded direct model)."""

        groups = (("intRat", 32, 0, "rfWen"), ("fpRat", 32, 0, "fpWen"),
                  ("vecRat", 31, 1, "vecWen"), ("v0Rat", 1, 0, "v0Wen"),
                  ("vlRat", 1, 0, "vlWen"))
        for field, count, offset, wen_field in groups:
            for index in range(count):
                value: Any = self.ports[f"io_diffRatBase_{field}_{index}"]
                logical = index + offset
                for lane in range(6):
                    valid = self.ports[f"io_renameUpdates_{lane}_valid"]
                    ldest = self.ports[f"io_renameUpdates_{lane}_bits_ldest"]
                    enable = self.ports[f"io_renameUpdates_{lane}_bits_{wen_field}"]
                    hit = valid & enable & (ldest == logical)
                    value = Mux(hit, self.ports[f"io_renameUpdates_{lane}_bits_pdest"], value)
                self._eq(module, f"io_diffRat_{field}_{index}", value)
                assigned.add(f"io_diffRat_{field}_{index}")

    def _exception(self, module: Module, assigned: set[str]) -> None:
        """Select the first valid enqueued/writeback exception deterministically."""

        candidates = [self.ports[f"io_enq_{i}_valid"] for i in range(6)]
        candidates += [self.ports[f"io_wb_{i}_valid"] for i in range(13) if f"io_wb_{i}_valid" in self.ports]
        valid = _or(candidates)
        self._eq(module, "io_out_valid", valid)
        self._eq(module, "io_state_valid", valid)
        assigned.update({"io_out_valid", "io_state_valid"})
        # Prefer enq lane 0, then the first writeback lane; preserve each field
        # only when that candidate actually exposes it in the locked surface.
        for out_name, direction, _width in self.specs:
            if direction != "output" or not out_name.startswith(("io_out_bits_", "io_state_bits_")):
                continue
            suffix = out_name.split("_bits_", 1)[1]
            source_names = [
                f"io_enq_0_bits_{suffix}",
                *[f"io_wb_{i}_bits_{suffix}" for i in range(13)],
            ]
            source = next((self.ports[n] for n in source_names if n in self.ports), None)
            if source is not None:
                self._eq(module, out_name, source)
                assigned.add(out_name)

    def _rename_buffer(self, module: Module, assigned: set[str]) -> None:
        """Expose enqueue/commit information through the bounded RAB envelope."""

        p = self.ports
        req_valid = [p[f"io_req_{i}_valid"] for i in range(6)]
        any_req = _or(req_valid)
        for name, value in (("io_canEnq", ~p["io_redirect_valid"]),
                            ("io_canEnqForDispatch", ~p["io_redirect_valid"]),
                            ("io_commits_isCommit", any_req),
                            ("io_commits_isWalk", p["io_fromRob_walkEnd"]),
                            ("io_status_walkEnd", p["io_fromRob_walkEnd"]),
                            ("io_status_commitEnd", p["io_fromRob_commitSize"].any())):
            self._eq(module, name, value); assigned.add(name)
        for i in range(6):
            self._eq(module, f"io_commits_commitValid_{i}", req_valid[i])
            self._eq(module, f"io_commits_walkValid_{i}", Const(0))
            assigned.update({f"io_commits_commitValid_{i}", f"io_commits_walkValid_{i}"})
            for field in ("ldest", "pdest", "rfWen", "fpWen", "vecWen", "v0Wen", "vlWen", "isMove"):
                self._eq(module, f"io_commits_info_{i}_{field}", p[f"io_req_{i}_bits_{field}"])
                assigned.add(f"io_commits_info_{i}_{field}")
            self._eq(module, f"io_toVecExcpMod_logicPhyRegMap_{i}_valid", req_valid[i])
            self._eq(module, f"io_toVecExcpMod_logicPhyRegMap_{i}_bits_lreg", p[f"io_req_{i}_bits_ldest"])
            self._eq(module, f"io_toVecExcpMod_logicPhyRegMap_{i}_bits_preg", p[f"io_req_{i}_bits_pdest"][:7])
            assigned.update({f"io_toVecExcpMod_logicPhyRegMap_{i}_valid",
                             f"io_toVecExcpMod_logicPhyRegMap_{i}_bits_lreg",
                             f"io_toVecExcpMod_logicPhyRegMap_{i}_bits_preg"})

    def _snapshot(self, module: Module, assigned: set[str]) -> None:
        """Bounded four-slot snapshot generator."""

        for i in range(4):
            self._eq(module, f"io_snapshots_{i}_flag", self.ports["io_enqData_flag"])
            self._eq(module, f"io_snapshots_{i}_value", self.ports["io_enqData_value"])
            assigned.update({f"io_snapshots_{i}_flag", f"io_snapshots_{i}_value"})

    def _trace(self, module: Module, assigned: set[str], buffer: bool) -> None:
        """Copy trace blocks while retaining the ROB back-pressure signal."""

        p = self.ports
        commit = p["io_in_fromEncoder_enable"] & p["io_in_fromEncoder_stall"]
        target = "io_out_blockCommit" if buffer else "io_out_blockRobCommit"
        self._eq(module, target, commit); assigned.add(target)
        pairs = [("io_out_groups_blocks", "io_in_fromRob_blocks")] if buffer else [("io_out_toEncoder_blocks", "io_in_fromRob_blocks")]
        for out_prefix, in_prefix in pairs:
            count = 3
            for i in range(count):
                for field in ("valid", "bits_ftqOffset", "bits_tracePipe_itype",
                              "bits_tracePipe_iretire", "bits_tracePipe_ilastsize"):
                    on = f"{out_prefix}_{i}_{field}"
                    inn = f"{in_prefix}_{i}_{field}"
                    if on in p and inn in p:
                        self._eq(module, on, p[inn]); assigned.add(on)
        if not buffer:
            for i in range(3):
                on = f"io_out_toPcMem_blocks_{i}_valid"; inn = f"io_in_fromRob_blocks_{i}_valid"
                if on in p:
                    self._eq(module, on, p[inn]); assigned.add(on)
                on = f"io_out_toPcMem_blocks_{i}_bits_ftqIdx_value"; inn = f"io_in_fromRob_blocks_{i}_bits_ftqIdx_value"
                if on in p:
                    self._eq(module, on, p[inn]); assigned.add(on)

    def _eq(self, module: Module, name: str, value: Any) -> None:
        """Install one output assignment if the frozen port exists."""

        if name in self.ports:
            module.d.comb += self.ports[name].eq(value)

    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        self._domain(module)
        assigned: set[str] = set()
        if self.member == "CompressUnit":
            self._compress(module, assigned)
        elif self.member == "DiffRatStateBuffer":
            self._diffrat(module, assigned)
        elif self.member == "ExceptionGen":
            self._exception(module, assigned)
        elif self.member == "RenameBuffer":
            self._rename_buffer(module, assigned)
        elif self.member == "SnapshotGenerator":
            self._snapshot(module, assigned)
        elif self.member == "Trace":
            self._trace(module, assigned, False)
        elif self.member == "TraceBuffer":
            self._trace(module, assigned, True)
        # SRAM leaves intentionally expose deterministic zero reads; writes are
        # represented by the locked W/R ports and are closed by parent memory gates.
        self._defaults(module, assigned)
        return module


class RobRenameTraceFamily(Elaboratable):
    """Aggregate shell; selected members are emitted individually by default."""

    def __init__(self, member: str = "ExceptionGen") -> None:
        self.member = member
        self.child = _LockedMember(member)

    def elaborate(self, platform: Any) -> Module:
        del platform
        module = Module()
        module.submodules.member = self.child
        return module


def build_verilog(configuration: Any = None, injected_dependencies: Any = None) -> str:
    """Emit one exact locked member. / 输出一个精确锁定端口成员。"""

    del injected_dependencies
    member = "ExceptionGen"
    if isinstance(configuration, dict):
        member = str(configuration.get("module", member))
    elif isinstance(configuration, str):
        member = configuration
    top = _LockedMember(member)
    return verilog.convert(top, name=member, ports=top.all_ports, emit_src=False)


def main() -> None:
    print(build_verilog({"module": COVERED_MODULES[0]}))


if __name__ == "__main__":
    main()
