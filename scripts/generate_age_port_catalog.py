"""Generate explicit locked AgeFamily port catalog from pinned hierarchy."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Regcache.AgeFamily-Hardware.py"
HIER = ROOT / "validation/v2-locked-hierarchy.json"
MEMBERS = ("NewAgeDetector", "NewAgeDetector_6", "RegCacheAgeDetector", "RegCacheAgeDetector_1", "RegCacheAgeTimer", "RegCacheAgeTimer_1", "RegCacheDataModule", "RegCacheDataModule_1", "RegCacheTagModule", "RegCacheTagModule_1")


def width(token: str) -> int:
    """Parse a V2 ANSI range."""

    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def render(data: dict[str, object]) -> str:
    """Render a multiline immutable port literal."""

    lines = ["# BEGIN LOCKED PORT CATALOG", "LOCKED_PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {"]
    for member in MEMBERS:
        lines.append(f'    "{member}": (')
        for port in data[member]["ports"]:  # type: ignore[index]
            lines.extend([
                "        (",
                f'            "{port["name"]}",',
                f'            "{port["direction"]}",',
                f'            {width(str(port.get("width", "")))},',
                "        ),",
            ])
        lines.append("    ),")
    lines.extend(["}", "PORT_SPECS = LOCKED_PORT_SPECS", "# END LOCKED PORT CATALOG"])
    return "\n".join(lines)


def main() -> None:
    """Replace only the marked catalog block."""

    text = TARGET.read_text(encoding="utf-8")
    start = text.index("# BEGIN LOCKED PORT CATALOG")
    end = text.index("# END LOCKED PORT CATALOG", start) + len("# END LOCKED PORT CATALOG")
    hierarchy = json.loads(HIER.read_text(encoding="utf-8"))["modules"]
    TARGET.write_text(text[:start] + render(hierarchy) + text[end:], encoding="utf-8", newline="\n")
    print("generated", TARGET)


if __name__ == "__main__":
    main()
