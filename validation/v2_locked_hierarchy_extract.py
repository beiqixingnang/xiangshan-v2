"""Extract the locked V2 XSTop hierarchy (modules, ports, child instances).

提取锁定 V2 XSTop 层级（模块、端口、子实例）。

Read-only migration tooling.  It parses the pinned ``XSTop.sv`` once and emits a
machine-readable hierarchy inventory that the parent-closure validators and the
rewrite workers consume.  It never modifies the locked artifact.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

REFERENCE = Path("/home/lishuo/xs-v2-local/build/rtl/XSTop.sv")
OUT = Path("/mnt/d/知识库开发/Unifier-Hardware-System/.agents/xiangshan-v2/validation/v2-locked-hierarchy.json")
EXPECTED_SHA = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"

MODULE_START = re.compile(r"^module\s+([A-Za-z_][A-Za-z0-9_]*)")
MODULE_END = re.compile(r"^endmodule\b")
PROV = re.compile(r"//\s*([^\s,]+?\.scala):(\d+):(\d+)\s*$")
DIR_RE = re.compile(r"^\s*(input|output|inout)\b\s*(\[[^\]]*\])?\s*(.*)$")
CONT_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*,?\s*$")
INST_RE = re.compile(r"^\s{2}([A-Za-z_][A-Za-z0-9_]*)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(#\s*\(.*?\)\s*)?\(")
NET_RE = re.compile(r"^\s{2}(wire|reg|logic)\b")


def parse_header(lines):
    ports = []
    direction = None
    width = ""
    for raw in lines:
        text = raw.split("//", 1)[0].strip()
        if not text:
            continue
        m = DIR_RE.match(text)
        if m:
            direction = m.group(1)
            width = (m.group(2) or "").strip()
            rest = m.group(3)
        else:
            rest = text
        if direction is None:
            continue
        rest = rest.rstrip(",").strip()
        if not rest or rest in {"(", ")"}:
            continue
        for token in rest.split(","):
            name = token.strip().strip("();")
            if name and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                ports.append({"name": name, "direction": direction, "width": width})
    return ports


def main() -> int:
    digest = hashlib.sha256()
    with REFERENCE.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
    sha = digest.hexdigest()
    if sha != EXPECTED_SHA:
        print(f"locked artifact mismatch: {sha}", file=sys.stderr)
        return 2

    modules: dict[str, dict] = {}
    current = None
    header: list[str] = []
    in_header = False
    scala_sources: list[str] = []
    children: list[dict] = []
    start_line = 0

    with REFERENCE.open("r", encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, 1):
            if current is None:
                m = MODULE_START.match(line)
                if m:
                    current = m.group(1)
                    start_line = number
                    header = [line]
                    in_header = True
                    scala_sources = []
                    children = []
                    p = PROV.search(line.rstrip())
                    if p:
                        scala_sources.append(f"{p.group(1)}:{p.group(2)}")
                continue
            if in_header:
                header.append(line)
                p = PROV.search(line.rstrip())
                if p and f"{p.group(1)}:{p.group(2)}" not in scala_sources:
                    scala_sources.append(f"{p.group(1)}:{p.group(2)}")
                if line.strip().endswith(");"):
                    in_header = False
                if MODULE_END.match(line):
                    modules[current] = {
                        "start_line": start_line,
                        "end_line": number,
                        "scala_sources": scala_sources,
                        "ports": parse_header(header),
                        "children": children,
                    }
                    current = None
                continue
            if MODULE_END.match(line):
                modules[current] = {
                    "start_line": start_line,
                    "end_line": number,
                    "scala_sources": scala_sources,
                    "ports": parse_header(header),
                    "children": children,
                }
                current = None
                continue
            m = INST_RE.match(line)
            if m and not NET_RE.match(line):
                child_module = m.group(1)
                # Chisel/Verilog-generated wrappers may use lower-case module
                # names (for example ``imsic_bus_top``).  The locked XSTop
                # explicitly instantiates these; filtering by uppercase loses
                # real parent-child closure edges.
                if child_module not in {"module", "wire", "reg", "logic"}:
                    p = PROV.search(line.rstrip())
                    children.append({
                        "module": child_module,
                        "instance": m.group(2),
                        "scala": f"{p.group(1)}:{p.group(2)}" if p else "",
                    })
    for entry in modules.values():
        entry["port_count"] = len(entry["ports"])
        entry["child_count"] = len(entry["children"])

    def tree(name, depth=0, seen=None):
        seen = seen or set()
        node = modules.get(name)
        if node is None:
            return {"module": name, "missing": True}
        result = {
            "module": name,
            "ports": node["port_count"],
            "scala_sources": node["scala_sources"][:10],
            "children": [],
        }
        if depth >= 6 or name in seen:
            return result
        seen = seen | {name}
        for child in node["children"]:
            result["children"].append(tree(child["module"], depth + 1, seen))
        return result

    root_children = modules["XSTop"]["children"]
    out = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_LOCKED_HIERARCHY",
        "reference_path": str(REFERENCE),
        "reference_sha256": sha,
        "module_count": len(modules),
        "modules": modules,
        "xstop_children": root_children,
        "xstop_tree": [tree(child["module"]) for child in root_children],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "modules": len(modules),
        "xstop_children": [c["module"] for c in root_children],
        "xstop_ports": modules["XSTop"]["port_count"],
        "out_bytes": OUT.stat().st_size,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
