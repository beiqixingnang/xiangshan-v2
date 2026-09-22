"""Utility-specific ABI parsing for the locked ClockGate primitive.

The shared strict-family rail predates the hand-written ClockGate reference and
only recognizes generated Chisel declarations.  This small diagnostic parser
keeps the typed-net normalization local to the Utility ResidualFamily audit;
it deliberately does not change the shared rail or any locked reference.
"""

from __future__ import annotations

import re
from pathlib import Path


Port = tuple[str, int]

_DECLARATION = re.compile(
    r"^(input|output|inout)\s+"
    r"(?:(?:wire|reg|logic|tri|signed|unsigned)\s+)*"
    r"(?:\[\s*(\d+)\s*:\s*0\s*\]\s*)?"
    r"([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)$"
)
def _strip_comment(line: str) -> str:
    """Remove a line comment while retaining declaration text."""

    return re.sub(r"//.*", "", line).strip()


def _declaration(line: str) -> tuple[str, int, list[str]] | None:
    """Parse one Verilog port declaration, including typed nets."""

    match = _DECLARATION.match(line.rstrip(",;").strip())
    if match is None:
        return None
    direction = str(match.group(1))
    width = int(match.group(2)) + 1 if match.group(2) else 1
    names = [item.strip() for item in match.group(3).split(",") if item.strip()]
    return direction, width, names


def parse_module_ports(rtl: str, module: str) -> dict[str, Port]:
    """Return direction/width ports from ANSI or non-ANSI Verilog headers.

    Generated Chisel references put declarations inside the module header,
    whereas the locked ClockGate uses a bare name list followed by body
    declarations such as ``input wire TE``.  Both forms are accepted, while
    declarations from a later child module are excluded.
    """

    header = re.search(
        r"\bmodule\s+" + re.escape(module) + r"\s*\((.*?)\)\s*;", rtl, re.S
    )
    if header is None:
        return {}

    ports: dict[str, Port] = {}
    header_lines = [_strip_comment(raw).rstrip(",").strip()
                    for raw in header.group(1).splitlines()]
    for line in header_lines:
        parsed = _declaration(line)
        if parsed is None:
            continue
        direction, width, names = parsed
        for name in names:
            ports[name] = (direction, width)

    # A non-ANSI header contains only bare names; declarations follow the
    # closing ``);``.  Restrict the scan to this module's body.
    wanted = {
        item.strip()
        for item in re.sub(r"//.*", "", header.group(1)).replace("\n", " ").split(",")
        if item.strip()
    }
    if wanted:
        body = rtl[header.end():]
        endmodule = re.search(r"\bendmodule\b", body)
        if endmodule is not None:
            body = body[:endmodule.start()]
        for raw in body.splitlines():
            parsed = _declaration(_strip_comment(raw))
            if parsed is None:
                continue
            direction, width, names = parsed
            for name in names:
                if name in wanted and name not in ports:
                    ports[name] = (direction, width)
    return ports


def parse_reference(path: Path, module: str = "ClockGate") -> dict[str, Port]:
    """Read and parse one locked reference without modifying it."""

    return parse_module_ports(path.read_text(encoding="utf-8"), module)


CLOCKGATE_PORTS: dict[str, Port] = {
    "TE": ("input", 1),
    "E": ("input", 1),
    "CK": ("input", 1),
    "Q": ("output", 1),
}


__all__ = ["CLOCKGATE_PORTS", "Port", "parse_module_ports", "parse_reference"]
