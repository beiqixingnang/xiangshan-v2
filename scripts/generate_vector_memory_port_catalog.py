"""Freeze the vector/memory aggregate's exact locked ANSI catalog."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Vector.Family-Hardware.py"
MEMBERS = (
    "VLMergeBufferImp",
    "VSMergeBufferImp",
    "VSegmentUnit",
    "VfofBuffer",
    "VirtualLoadQueue",
    "VldMergeUnit",
    "VsetModule",
)


def width(token: str) -> int:
    """Parse one locked Verilog range width. / 解析锁定 Verilog 范围位宽。"""

    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def main() -> None:
    """Replace only the marked catalog block. / 仅替换标记的端口目录区块。"""

    hierarchy = json.loads((ROOT / "validation/v2-locked-hierarchy.json").read_text(encoding="utf-8"))["modules"]
    lines = [
        "# BEGIN LOCKED PORT CATALOG",
        "# Exact V2 ANSI names, directions, widths, and declaration order. / 精确 V2 ANSI 名称、方向、位宽与声明顺序。",
        "LOCKED_PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {",
    ]
    for member in MEMBERS:
        lines.append(f'    "{member}": (')
        for port in hierarchy[member]["ports"]:
            lines.extend([
                "        (",
                f'            "{port["name"]}",',
                f'            "{port["direction"]}",',
                f'            {width(str(port.get("width", "")))},',
                "        ),",
            ])
        lines.append("    ),")
    lines.extend(["}", "PORT_SPECS = LOCKED_PORT_SPECS", "# END LOCKED PORT CATALOG"])
    text = TARGET.read_text(encoding="utf-8")
    start = text.index("# BEGIN LOCKED PORT CATALOG")
    end = text.index("# END LOCKED PORT CATALOG", start) + len("# END LOCKED PORT CATALOG")
    TARGET.write_text(text[:start] + "\n".join(lines) + text[end:], encoding="utf-8", newline="\n")
    print(f"generated {TARGET} ({sum(len(hierarchy[m]['ports']) for m in MEMBERS)} ports)")


if __name__ == "__main__":
    main()
