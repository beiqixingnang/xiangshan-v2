"""Freeze the DCache miss/queue family's exact locked port catalog.

This generator is deliberately narrow: it replaces only the marked catalog in
the one family Build, deriving port name, direction, width, and declaration
order from the immutable V2 locked hierarchy.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
TARGET = (
    ROOT
    / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory"
    / "Build-Cpu.Memory.Dcache.MissQueue.Family-Hardware.py"
)
MEMBERS = (
    "CMOUnit",
    "MissEntry",
    "MissReadyGen",
    "ProbeEntry",
    "TreeArbiter",
    "WritebackEntry",
    "WritebackEntry_15",
)


def width(token: str) -> int:
    """Parse one locked ANSI range into a positive signal width."""

    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def render(modules: dict[str, object]) -> str:
    """Render a literal, explicit, ordered port catalog."""

    lines = [
        "# BEGIN LOCKED PORT CATALOG",
        "# Generated from validation/v2-locked-hierarchy.json; do not hand-edit.",
        "LOCKED_PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {",
    ]
    for member in MEMBERS:
        node = modules[member]
        if not isinstance(node, dict):
            raise TypeError(member)
        ports = node["ports"]
        if not isinstance(ports, list):
            raise TypeError(member)
        lines.append(f'    "{member}": (')
        for port in ports:
            if not isinstance(port, dict):
                raise TypeError(member)
            lines.append(
                f'        ({port["name"]!r}, {port["direction"]!r}, '
                f'{width(str(port.get("width", "")))!r}),'
            )
        lines.append("    ),")
    lines.extend([
        "}",
        "PORT_SPECS = LOCKED_PORT_SPECS",
        "# END LOCKED PORT CATALOG",
    ])
    return "\n".join(lines)


def main() -> None:
    """Replace only the target's generated catalog marker block."""

    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))["modules"]
    if not isinstance(hierarchy, dict):
        raise TypeError("modules")
    text = TARGET.read_text(encoding="utf-8")
    begin = text.index("# BEGIN LOCKED PORT CATALOG")
    end_marker = "# END LOCKED PORT CATALOG"
    end = text.index(end_marker, begin) + len(end_marker)
    TARGET.write_text(
        text[:begin] + render(hierarchy) + text[end:],
        encoding="utf-8",
        newline="\n",
    )
    print(f"generated {TARGET.relative_to(ROOT)} ({sum(len(hierarchy[m]['ports']) for m in MEMBERS)} ports)")


if __name__ == "__main__":
    main()
