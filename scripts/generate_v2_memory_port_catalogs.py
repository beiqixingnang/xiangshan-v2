"""Freeze exact locked port catalogs into the V2 memory-family Builds.

This is a one-shot mechanical generator used to replace pattern-derived port
surfaces with explicit name/direction/width/order declarations.  It only edits
the four marked Build files under this auxiliary repository.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
TARGETS = {
    "Build-Cpu.Memory.MemCommon-Pipeline-Hardware.py": (
        "PipelineRegModule", "PipelineRegModule_1", "PipelineRegModule_2", "PipelineRegModule_6",
    ),
    "Build-Cpu.Memory.Lsqueue.LoadQueueData-Hardware.py": (
        "LqMaskModule", "LqPAddrModule", "LqPAddrModule_1", "LqVAddrModule",
    ),
    "Build-Cpu.Memory.Lsqueue.StoreQueueData-Hardware.py": (
        "SQAddrModule", "SQAddrModule_1", "SQData8Module", "SQDataModule",
    ),
    "Build-Cpu.Memory.Dcache.MetaArray-Hardware.py": (
        "L1CohMetaArray", "L1ErrorMetaArray", "L1FlagMetaArray", "L1PrefetchSourceArray",
    ),
}


def width(token: str) -> int:
    """Parse a locked Verilog range. / 解析锁定 Verilog 范围。"""

    import re

    match = re.search(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", token)
    return abs(int(match.group(1)) - int(match.group(2))) + 1 if match else 1


def render(module_names: tuple[str, ...], hierarchy: dict[str, object]) -> str:
    """Render one explicit immutable port catalog. / 渲染一个显式不可变端口目录。"""

    lines = [
        "# BEGIN LOCKED PORT CATALOG",
        "# Exact V2 ANSI names, directions, widths, and declaration order. / 精确 V2 ANSI 名称、方向、位宽与声明顺序。",
        "LOCKED_PORT_SPECS: dict[str, tuple[tuple[str, str, int], ...]] = {",
    ]
    for module_name in module_names:
        lines.append(f'    "{module_name}": (')
        for port in hierarchy[module_name]["ports"]:  # type: ignore[index]
            name = str(port["name"])
            direction = str(port["direction"])
            bit_width = width(str(port.get("width", "")))
            lines.extend([
                "        (",
                f'            "{name}",',
                f'            "{direction}",',
                f"            {bit_width},",
                "        ),",
            ])
        lines.append("    ),")
    lines.extend([
        "}",
        "PORT_SPECS = LOCKED_PORT_SPECS",
        "# END LOCKED PORT CATALOG",
    ])
    return "\n".join(lines)


def main() -> None:
    """Update only marked catalog blocks. / 只更新标记的目录区块。"""

    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))["modules"]
    for filename, modules in TARGETS.items():
        path = next(ROOT.glob(f"python/Program-System/System-Build/Build-Cpu/**/{filename}"))
        text = path.read_text(encoding="utf-8")
        start = text.index("# BEGIN LOCKED PORT CATALOG")
        end_marker = "# END LOCKED PORT CATALOG"
        end = text.index(end_marker, start) + len(end_marker)
        updated = text[:start] + render(modules, hierarchy) + text[end:]
        path.write_text(updated.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
        print(path.relative_to(ROOT), sum(1 for _ in updated.splitlines()))


if __name__ == "__main__":
    main()
