"""Freeze explicit V2 decode/control port catalog from locked hierarchy."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Decode.ControlFamily-Hardware.py"
MEMBERS = ("Backend", "DecodeUnit", "FusionDecoder", "UopInfoGen", "FPDecoder", "VTypeGen", "VecExceptionGen", "VIAluDecoder")


def width(token: str) -> int:
    """Parse an ANSI range width."""

    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def main() -> None:
    """Replace only the catalog marker block."""

    data = json.loads((ROOT / "validation/v2-locked-hierarchy.json").read_text(encoding="utf-8"))["modules"]
    lines = ["# BEGIN LOCKED PORT CATALOG", "LOCKED_PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {"]
    for member in MEMBERS:
        lines.append(f'    "{member}": (')
        for port in data[member]["ports"]:
            lines.extend(["        (", f'            "{port["name"]}",', f'            "{port["direction"]}",', f'            {width(str(port.get("width", "")))},', "        ),"])
        lines.append("    ),")
    lines.extend(["}", "PORT_SPECS = LOCKED_PORT_SPECS", "# END LOCKED PORT CATALOG"])
    text = TARGET.read_text(encoding="utf-8"); start = text.index("# BEGIN LOCKED PORT CATALOG"); end = text.index("# END LOCKED PORT CATALOG", start) + len("# END LOCKED PORT CATALOG")
    TARGET.write_text(text[:start] + "\n".join(lines) + text[end:], encoding="utf-8", newline="\n")
    print("generated", TARGET)


if __name__ == "__main__":
    main()
