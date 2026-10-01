"""Standalone XRet CSR permission leaf for the V2 NewCSR control family.

The port names and equations are taken from the locked
``XRetPermitModule.scala`` semantics.  The sibling CSR permit members stay in
their aggregate Build and are intentionally outside this focused leaf.
"""

from __future__ import annotations

from typing import Any

from amaranth import Const, Elaboratable, Module, Signal
from amaranth.back import verilog


# =============================================================================
# Module Contract
# =============================================================================
COVERED_MODULES = ("XRetPermitModule",)
PORT_SPECS = (
    ("io_in_privState_PRVM", "input", 2),
    ("io_in_privState_V", "input", 1),
    ("io_in_debugMode", "input", 1),
    ("io_in_xRet_mnret", "input", 1),
    ("io_in_xRet_mret", "input", 1),
    ("io_in_xRet_sret", "input", 1),
    ("io_in_xRet_dret", "input", 1),
    ("io_in_status_tsr", "input", 1),
    ("io_in_status_vtsr", "input", 1),
    ("io_out_Xret_EX_II", "output", 1),
    ("io_out_Xret_EX_VI", "output", 1),
    ("io_out_hasLegalMNret", "output", 1),
    ("io_out_hasLegalMret", "output", 1),
    ("io_out_hasLegalSret", "output", 1),
    ("io_out_hasLegalDret", "output", 1),
)
__all__ = ["COVERED_MODULES", "PORT_SPECS", "PermitModule", "build_verilog", "main"]


# =============================================================================
# Configuration
# =============================================================================
# XRetPermitModule is fixed-width by the locked V2 hierarchy.


# =============================================================================
# Implementation
# =============================================================================
class PermitModule(Elaboratable):
    """Combinational XRet legality equations from CSRPermitModule.scala."""

    def __init__(self, name: str = "XRetPermitModule") -> None:
        if name != COVERED_MODULES[0]:
            raise ValueError(name)
        self.name = name
        self.specs = PORT_SPECS
        self.ports = {
            port: Signal(width, name=port)
            for port, _direction, width in PORT_SPECS
        }
        for port, signal in self.ports.items():
            setattr(self, port, signal)

    def elaborate(self, platform: Any) -> Module:
        del platform
        p = self.ports
        module = Module()
        mode_m = p["io_in_privState_PRVM"] == Const(3, 2)
        mode_hu = (p["io_in_privState_PRVM"] == Const(0, 2)) & ~p["io_in_privState_V"]
        mode_hs = (p["io_in_privState_PRVM"] == Const(1, 2)) & ~p["io_in_privState_V"]
        mode_vu = (p["io_in_privState_PRVM"] == Const(0, 2)) & p["io_in_privState_V"]
        mode_vs = (p["io_in_privState_PRVM"] == Const(1, 2)) & p["io_in_privState_V"]

        mnret_illegal = p["io_in_xRet_mnret"] & ~mode_m
        mret_illegal = p["io_in_xRet_mret"] & ~mode_m
        sret_ii = p["io_in_xRet_sret"] & (mode_hu | (mode_hs & p["io_in_status_tsr"]))
        sret_vi = p["io_in_xRet_sret"] & (mode_vu | (mode_vs & p["io_in_status_vtsr"]))
        dret_illegal = p["io_in_xRet_dret"] & ~p["io_in_debugMode"]

        module.d.comb += [
            p["io_out_Xret_EX_II"].eq(mnret_illegal | mret_illegal | sret_ii | dret_illegal),
            p["io_out_Xret_EX_VI"].eq(sret_vi),
            p["io_out_hasLegalMNret"].eq(p["io_in_xRet_mnret"] & ~mnret_illegal),
            p["io_out_hasLegalMret"].eq(p["io_in_xRet_mret"] & ~mret_illegal),
            p["io_out_hasLegalSret"].eq(p["io_in_xRet_sret"] & ~(sret_ii | sret_vi)),
            p["io_out_hasLegalDret"].eq(p["io_in_xRet_dret"] & ~dret_illegal),
        ]
        return module


# =============================================================================
# Public Adapter
# =============================================================================
def build_verilog(configuration: Any = None, injected_dependencies: Any = None) -> str:
    """Emit one deterministic XRetPermitModule Verilog module."""

    del injected_dependencies
    if configuration is not None:
        selected = configuration.get("module", configuration.get("name")) if isinstance(configuration, dict) else configuration
        if selected not in (None, "XRetPermitModule"):
            raise KeyError(selected)
    top = PermitModule()
    return verilog.convert(top, name="XRetPermitModule",
                           ports=[top.ports[name] for name, _direction, _width in PORT_SPECS],
                           emit_src=False)


# =============================================================================
# Direct Entry
# =============================================================================
def main() -> None:
    print(build_verilog())


if __name__ == "__main__":
    main()
