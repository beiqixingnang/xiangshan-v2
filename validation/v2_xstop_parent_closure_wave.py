"""Validate the bounded Kunminghu V2 parent/top closure wave.

The wave joins the seven frozen port envelopes (XSCore, Frontend, Backend,
MemBlock, L2Top, XSTile, and XSTop), exercises the real injected child edges
that are currently available, and records every absent child explicitly.  It
never treats a bounded parent or a passing lint gate as strict equivalence.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from amaranth.back import verilog


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "python/Program-System/System-Build/Build-Cpu"
TEST = ROOT / "python/Program-System/System-Testing/Testing-Cpu"
INVENTORY = ROOT / "validation/v2-root-port-inventories.json"
MEM_INVENTORY = ROOT / "validation/v2-memblock-port-inventory.json"
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
REFERENCE = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
COMPACT_ROOTS = {name: ROOT / f"validation/reference-sv/{name}.sv"
                 for name in ("XSCore", "L2Top", "XSTile", "XSTop")}
OUTPUT = ROOT / "validation/v2-xstop-parent-closure-wave-results.json"
WORK = ROOT / "validation/.work/v2-xstop-parent-closure-wave"

SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
REFERENCE_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
REFERENCE_BYTES = 228590583

TARGETS = {
    "xs_core": BUILD / "Cpu-Core/Cpu-Core-Top.UHSCore.Parent-Hardware.py",
    "roots": BUILD / "Cpu-Core/Cpu-Core-Top.UHSC.Roots-Hardware.py",
    "frontend": BUILD / "Cpu-Core/Cpu-Core-Frontend.Top-Hardware.py",
    "backend": BUILD / "Cpu-Core/Cpu-Core-Backend.Top-Hardware.py",
    "memblock": BUILD / "Cpu-Memory/Cpu-Memory-Memory.MemBlock-Hardware.py",
    "intbuffer": BUILD / "Cpu-Core/Cpu-Core-Top.UHSTile.IntBuffer.Family-Hardware.py",
    "coupled_l2": BUILD / "Cpu-Memory/Cpu-Memory-Dependency.CoupledL2.Directory-Hardware.py",
}

ROOT_MAP = {"XSCore": "UHSCore", "L2Top": "L2Top", "XSTile": "UHSTile", "XSTop": "UHSCTop"}
def digest(path: Path) -> str:
    """Hash one immutable or generated file. / 计算不可变或生成文件摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path: Path, name: str) -> Any:
    """Load one hyphenated Build file by explicit path. / 按显式路径加载 Build。"""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def port_rows(source_root: str) -> list[dict[str, Any]]:
    """Return one frozen root inventory. / 返回一个冻结根端口清单。"""

    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
    if payload.get("source_commit") != SOURCE_COMMIT or payload.get("reference_sha256") != REFERENCE_SHA256:
        raise RuntimeError("root inventory baseline mismatch")
    rows = payload["modules"][source_root]["ports"]
    if len(rows) != int(payload["modules"][source_root]["port_count"]):
        raise RuntimeError(f"{source_root} inventory count mismatch")
    return rows


def inventory_width(value: Any) -> int:
    """Normalize a frozen width field. / 规范化冻结位宽字段。"""

    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and text.endswith("]") and ":" in text:
            high, low = text[1:-1].split(":", 1)
            return max(1, abs(int(high) - int(low)) + 1)
    return max(1, int(value or 1))


def _extract_instance_pins(text: str, module_name: str, instance_name: str) -> tuple[str, list[tuple[str, str]]]:
    """Parse one exact instance pin list without inferring assignments.
    精确解析一个实例 pin 列表，不推断网络赋值。
    """

    start = re.search(rf"(?m)^\s*({re.escape(module_name)})\s+{re.escape(instance_name)}\s*\(", text)
    if start is None:
        raise ValueError(f"instance not found: {module_name} {instance_name}")
    open_paren = text.find("(", start.start())
    depth = 0
    close_paren = -1
    for index in range(open_paren, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                close_paren = index
                break
    if close_paren < 0:
        raise ValueError(f"unterminated instance: {instance_name}")
    block = re.sub(r"//[^\n]*", "", text[open_paren + 1:close_paren])
    pins: list[tuple[str, str]] = []
    cursor = 0
    while True:
        match = re.search(r"\.([A-Za-z_][A-Za-z0-9_$]*)\s*\(", block[cursor:])
        if match is None:
            break
        pin_name = match.group(1)
        pin_open = cursor + match.end() - 1
        depth = 0
        pin_close = -1
        for index in range(pin_open, len(block)):
            if block[index] == "(":
                depth += 1
            elif block[index] == ")":
                depth -= 1
                if depth == 0:
                    pin_close = index
                    break
        if pin_close < 0:
            raise ValueError(f"unterminated pin: {instance_name}.{pin_name}")
        expression = " ".join(block[pin_open + 1:pin_close].split())
        pins.append((pin_name, expression))
        cursor = pin_close + 1
    return str(start.group(1)), pins


def exact_root_pin_maps(hierarchy: dict[str, Any]) -> dict[str, Any]:
    """Verify compact roots against the locked artifact and enumerate pin maps.

    The complete map is validation evidence. Builds receive selected
    width-checked endpoints only, never source paths, hashes, or the full map.
    / 完整接线表仅写入验证证据；Build 仅接收经位宽检查的端点边。
    """

    root_tables: dict[str, Any] = {}
    for root_name, compact_path in COMPACT_ROOTS.items():
        record = hierarchy.get("modules", {}).get(root_name)
        if not isinstance(record, dict):
            raise RuntimeError(f"missing hierarchy record: {root_name}")
        start_line = int(record["start_line"])
        end_line = int(record["end_line"])
        captured: list[bytes] = []
        with REFERENCE.open("rb") as stream:
            for line_no, line in enumerate(stream, 1):
                if line_no < start_line:
                    continue
                if line_no > end_line:
                    break
                captured.append(line)
        locked_module = b"".join(captured)
        compact_module = compact_path.read_bytes()
        exact_slice = locked_module == compact_module
        if not exact_slice:
            raise RuntimeError(f"compact root differs from locked module span: {root_name}")
        text = compact_module.decode("utf-8", "replace")
        root_ports = {str(row["name"]): row for row in record.get("ports", [])}
        pin_rows: list[dict[str, Any]] = []
        errors: list[str] = []
        for child in record.get("children", []):
            child_module = str(child["module"])
            instance = str(child["instance"])
            child_record = hierarchy.get("modules", {}).get(child_module, {})
            child_ports = {str(row["name"]): row for row in child_record.get("ports", [])}
            try:
                parsed_module, parsed_pins = _extract_instance_pins(text, child_module, instance)
            except ValueError as error:
                errors.append(str(error))
                continue
            for port, net in parsed_pins:
                spec = child_ports.get(port)
                if spec is None:
                    errors.append(f"pin absent from hierarchy interface: {instance}.{port}")
                    continue
                pin_rows.append({"instance": instance, "module": parsed_module, "port": port,
                                 "net": net, "direction": str(spec.get("direction", "")),
                                 "width": inventory_width(spec.get("width", "")),
                                 "lineage": "exact_instance_port_net"})
            expected_ports = int(child_record.get("port_count", -1))
            if len(parsed_pins) != expected_ports:
                errors.append(f"{instance}: pins={len(parsed_pins)}, interface={expected_ports}")

        by_net: dict[str, list[dict[str, Any]]] = {}
        for pin in pin_rows:
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", pin["net"]):
                by_net.setdefault(pin["net"], []).append({
                    "kind": "child", "child": pin["instance"], "module": pin["module"],
                    "port": pin["port"], "direction": pin["direction"], "width": pin["width"],
                })
        for net, spec in root_ports.items():
            by_net.setdefault(net, []).append({"kind": "parent", "port": net,
                "direction": str(spec.get("direction", "")),
                "width": inventory_width(spec.get("width", ""))})

        net_groups: list[dict[str, Any]] = []
        verified_edges: list[dict[str, Any]] = []
        for net, endpoints in sorted(by_net.items()):
            if len(endpoints) < 2:
                continue
            drivers = [endpoint for endpoint in endpoints
                       if (endpoint["kind"] == "child" and endpoint["direction"] == "output")
                       or (endpoint["kind"] == "parent" and endpoint["direction"] == "input")]
            sinks = [endpoint for endpoint in endpoints
                     if (endpoint["kind"] == "child" and endpoint["direction"] == "input")
                     or (endpoint["kind"] == "parent" and endpoint["direction"] == "output")]
            direction_ok = len(drivers) == 1 and bool(sinks)
            width_ok = direction_ok and all(int(endpoint["width"]) == int(drivers[0]["width"]) for endpoint in sinks)
            if width_ok:
                source = {key: value for key, value in drivers[0].items() if key in {"kind", "child", "port"}}
                destinations = [{key: value for key, value in endpoint.items()
                                 if key in {"kind", "child", "port"}} for endpoint in sinks]
                verified_edges.append({"source": source, "destinations": destinations,
                                       "width": int(drivers[0]["width"]), "net": net})
            net_groups.append({"net": net, "endpoints": endpoints, "driver_count": len(drivers),
                               "sink_count": len(sinks),
                               "direction_status": "PASS" if direction_ok else "PENDING_AMBIGUOUS_OR_OPEN",
                               "width_status": "PASS" if width_ok else "PENDING_WIDTH_MISMATCH"})
        resolved_pins = {
            (str(endpoint.get("child")), str(endpoint.get("port")))
            for edge in verified_edges
            for endpoint in (edge["source"], *edge["destinations"])
            if endpoint.get("kind") == "child"
        }
        unsupported_pins: list[dict[str, Any]] = []
        for pin in pin_rows:
            identity = (str(pin["instance"]), str(pin["port"]))
            if identity in resolved_pins:
                continue
            net = str(pin["net"])
            if re.fullmatch(r"\d*'[bBdDhHoO][0-9a-fA-FxXzZ_]+", net):
                reason = "constant_expression"
            elif net.startswith("{"):
                reason = "concatenation_expression"
            elif not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", net):
                reason = "nontrivial_expression"
            else:
                groups = next((item for item in net_groups if item["net"] == net), None)
                if groups is None or len(groups["endpoints"]) < 2:
                    reason = "unpaired_net"
                elif groups["direction_status"] != "PASS":
                    reason = "ambiguous_or_multidriver_net"
                elif groups["width_status"] != "PASS":
                    reason = "width_mismatch"
                else:
                    reason = "endpoint_not_bound"
            unsupported_pins.append({**pin, "unsupported_reason": reason})
        unsupported_counts: dict[str, int] = {}
        for row in unsupported_pins:
            key = str(row["unsupported_reason"])
            unsupported_counts[key] = unsupported_counts.get(key, 0) + 1
        clock_reset = [row for row in pin_rows
                       if "clock" in row["port"].lower() or "reset" in row["port"].lower()]
        root_tables[root_name] = {
            "compact_path": compact_path.relative_to(ROOT).as_posix(),
            "compact_sha256": hashlib.sha256(compact_module).hexdigest(),
            "locked_module_span": {"start_line": start_line, "end_line": end_line,
                "bytes": len(locked_module), "sha256": hashlib.sha256(locked_module).hexdigest(),
                "exact_compact_match": exact_slice},
            "expected_direct_child_count": len(record.get("children", [])),
            "direct_child_count": len({row["instance"] for row in pin_rows}),
            "instance_pin_count": len(pin_rows),
            "instance_port_maps": pin_rows,
            "net_groups": net_groups,
            "clock_reset_edges": clock_reset,
            "verified_equal_width_edges": verified_edges,
            "verified_edge_count": sum(len(row["destinations"]) for row in verified_edges),
            "connected_child_pin_count": len(resolved_pins),
            "unsupported_pin_count": len(unsupported_pins),
            "unsupported_pin_counts_by_reason": unsupported_counts,
            "unsupported_pins": unsupported_pins,
            "unsupported_net_group_count": sum(row["direction_status"] != "PASS" or row["width_status"] != "PASS"
                                                for row in net_groups),
            "parse_errors": errors,
            "status": "PASS" if not errors and exact_slice else "FAIL",
        }
    return root_tables


def mem_rows() -> list[dict[str, Any]]:
    """Return the frozen 1326-port MemBlock inventory. / 返回冻结 MemBlock 清单。"""

    payload = json.loads(MEM_INVENTORY.read_text(encoding="utf-8"))
    rows = payload.get("ports", [])
    if payload.get("module") != "MemBlock" or len(rows) != 1326:
        raise RuntimeError("MemBlock inventory mismatch")
    return rows


def header_port_count(rtl: str, module_name: str) -> int:
    """Count ANSI ports in one generated top header. / 统计生成顶层 ANSI 端口。"""

    match = re.search(rf"\bmodule\s+{re.escape(module_name)}\s*\((.*?)\);", rtl, re.S)
    if match is None:
        return 0
    # Amaranth emits a compact name-only header and places declarations in a
    # separate section.  Count identifiers in the header, rather than only
    # ANSI direction tokens, so both forms remain ABI-auditable.
    return len(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", match.group(1)))


def generated_port_table(rtl: str, module_name: str) -> dict[str, tuple[str, int]]:
    """Parse emitted declaration names, directions, and widths. / 解析端口完整 ABI。"""

    module = re.search(rf"\bmodule\s+{re.escape(module_name)}\s*\((.*?)\);", rtl, re.S)
    if module is None:
        return {}
    end = re.search(r"(?m)^\s*endmodule\b", rtl[module.end():])
    body_end = module.end() + end.start() if end is not None else len(rtl)
    body = rtl[module.end():body_end]
    pattern = re.compile(
        r"(?m)^\s*(input|output|inout)\s+(?:\[(\d+)\s*:\s*(\d+)\]\s+)?"
        r"([A-Za-z_][A-Za-z0-9_$]*)\s*;"
    )
    result: dict[str, tuple[str, int]] = {}
    for match in pattern.finditer(body):
        width = 1 if match.group(2) is None else abs(int(match.group(2)) - int(match.group(3))) + 1
        result[match.group(4)] = (match.group(1), width)
    return result


def audit_abi(rtl: str, module_name: str, expected_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare every emitted name, direction, and width. / 比较所有名称、方向和位宽。"""

    expected = {str(row["name"]): (str(row["direction"]), inventory_width(row.get("width", "")))
                for row in expected_rows}
    actual = generated_port_table(rtl, module_name)
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    mismatches = [{"name": name, "expected": expected[name], "actual": actual[name]}
                  for name in sorted(set(expected) & set(actual)) if expected[name] != actual[name]]
    return {"status": "PASS" if not missing and not extra and not mismatches else "FAIL",
            "expected_count": len(expected), "actual_count": len(actual),
            "missing": missing, "extra": extra, "direction_width_mismatches": mismatches}


def run_wsl(command: str) -> dict[str, Any]:
    """Run one bounded Verilator/Yosys command in WSL. / 在 WSL 执行后端门禁。"""

    try:
        result = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command],
                                capture_output=True, check=False, timeout=300)
        output = (result.stdout + result.stderr).decode("utf-8", "replace")
        return {"status": "PASS" if result.returncode == 0 else "FAIL",
                "returncode": result.returncode, "output_tail": output[-1400:]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"status": "FAIL", "returncode": None, "output_tail": str(error)}


def linux_path(path: Path) -> str:
    """Convert a Windows path through the explicit WSL helper. / 通过 WSL helper 转路径。"""

    result = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(path)],
                            capture_output=True, check=True)
    return result.stdout.decode().strip()


def tool_gates(path: Path, module_name: str) -> dict[str, Any]:
    """Run Verilator and Yosys lint on one generated envelope. / 对包络运行 Verilator/Yosys。"""

    wsl = linux_path(path)
    verilator = run_wsl(f"verilator --lint-only --Wno-fatal --top-module {module_name} {wsl}")
    yosys = run_wsl(
        f"yosys -Q -p 'read_verilog -sv {wsl}; hierarchy -top {module_name}; proc; check'"
    )
    return {"verilator": verilator, "yosys": yosys,
            "status": "PASS" if verilator["status"] == yosys["status"] == "PASS" else "FAIL"}


def write_rtl(name: str, rtl: str) -> tuple[Path, dict[str, Any]]:
    """Persist one deterministic generated envelope for backend gates. / 保存确定性 RTL。"""

    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / f"{name}.sv"
    path.write_text(rtl, encoding="utf-8", newline="\n")
    return path, {"bytes": len(rtl.encode()), "sha256": digest(path)}


def direct_vectors(core: Any, roots: Any, hierarchy: dict[str, Any]) -> dict[str, Any]:
    """Exercise source parent equations and closure observations. / 执行父方程与闭环观测。"""

    mismatches: list[dict[str, Any]] = []
    for index in range(64):
        vector = {
            "frontend_valid": index & 1,
            "backend_can_accept": index % 3 != 0,
            "mem_a_valid": index % 4 != 0,
            "mem_a_ready": index % 5 != 0,
            "mem_d_valid": index % 6 == 0,
            "mem_d_ready": index % 2 == 0,
            "reset": index < 2,
            "child_missing": 3,
        }
        got = core.uhs_core_parent_observation(**vector)
        expected = {
            "frontend_backend_fire": int(vector["frontend_valid"] and vector["backend_can_accept"] and not vector["reset"]),
            "mem_a_fire": int(vector["mem_a_valid"] and vector["mem_a_ready"] and not vector["reset"]),
            "mem_d_fire": int(vector["mem_d_valid"] and vector["mem_d_ready"] and not vector["reset"]),
            "child_missing": 3,
            "closure_complete": 0,
        }
        if got != expected:
            mismatches.append({"index": index, "got": got, "expected": expected})
    root_checks: dict[str, Any] = {}
    root_product = {"XSCore": {"frontend": "frontend", "backend": "backend", "memBlock": "mem_block"},
                    "L2Top": {"inner_l2cache": "tl2tl_parent"},
                    "XSTile": {"core": "uhs_core", "l2top": "l2_top"},
                    "XSTop": {"core_with_l2": "xstile"}}
    expected_ports = {"XSCore": 308, "L2Top": 441, "XSTile": 153, "XSTop": 204}
    for root_name, mapping in root_product.items():
        rows = hierarchy["modules"][root_name]["children"]
        expected_names = tuple(str(row["instance"]) for row in rows)
        bound = tuple(instance for instance in expected_names if instance in mapping)
        status = {instance: "BOUNDARY" for instance in bound}
        root_checks[root_name] = roots.root_closure_observation(
            bound, expected_names, expected_ports[root_name], expected_ports[root_name], status)
        root_checks[root_name]["bound_binding_classes"] = {
            mapping[instance]: "BOUNDARY" for instance in bound
        }
    l2_children = tuple(str(row["instance"]) for row in hierarchy["modules"]["L2Top"]["children"])
    root_checks["L2Top"] = roots.root_closure_observation(
        ("inner_l2cache",), l2_children, 441, 441,
        {"inner_l2cache": "BOUNDARY"},
    )
    return {"status": "PASS" if not mismatches else "FAIL", "vectors": 64,
            "mismatches": mismatches, "root_observations": root_checks}


def remap_root_edges(pin_map: dict[str, Any]) -> list[dict[str, Any]]:
    """Strip evidence metadata from exact maps before Build injection. / 将证据字段移出 Build 注入。"""

    return [{"source": row["source"], "destinations": row["destinations"], "width": row["width"]}
            for row in pin_map.get("verified_equal_width_edges", [])]


def pin_audit(pin_map: dict[str, Any]) -> dict[str, Any]:
    """Pass compact edge coverage counts while keeping the pin list in evidence.
    仅传递接线覆盖计数；完整 pin 清单留在验证证据。
    """

    return {"pin_table_complete": pin_map.get("status") == "PASS",
            "expected_child_pin_count": pin_map.get("instance_pin_count", 0),
            "connected_child_pin_count": pin_map.get("connected_child_pin_count", 0),
            "unsupported_pin_count": pin_map.get("unsupported_pin_count", 0)}


def integrate_root(roots: Any, root_name: str, module_type: Any, ports: list[dict[str, Any]],
                   expected_children: list[str], children: dict[str, Any],
                   pin_map: dict[str, Any], module_name: str) -> dict[str, Any]:
    """Elaborate one root with exact injected edge groups only. / 用精确注入边展开一个 root。"""

    deps = {"full_port_specs": ports, "expected_children": expected_children,
            "children": children, "verified_pin_edges": remap_root_edges(pin_map),
            "verified_pin_audit": pin_audit(pin_map)}
    root = module_type(injected_dependencies=deps)
    rtl = verilog.convert(root, name=module_name, ports=list(root.full_inventory_ports), emit_src=False)
    second_rtl = verilog.convert(root, name=module_name, ports=list(root.full_inventory_ports), emit_src=False)
    path, file_info = write_rtl(module_name, rtl)
    bound_edges = {key: sorted(edges) for key, edges in root.bound_child_edges.items()}
    expected_count = sum(len(row["destinations"]) for row in remap_root_edges(pin_map))
    abi = audit_abi(rtl, module_name, ports)
    return {**file_info, "status": "BOUNDARY", "module": module_name,
            "expected_ports": len(ports), "generated_ports": header_port_count(rtl, module_name),
            "abi_status": abi["status"], "abi": abi,
            "deterministic": rtl == second_rtl,
            "instance_pin_count": pin_map.get("instance_pin_count", 0),
            "direct_equal_width_edge_candidates": expected_count,
            "unsupported_pin_count": pin_map.get("unsupported_pin_count", 0),
            "unsupported_pin_counts_by_reason": pin_map.get("unsupported_pin_counts_by_reason", {}),
            "rejected_verified_edges": root.missing_child_edges,
            "verified_edge_missing_count": root._verified_unsupported_pin_count + sum(
                len(rows) for rows in root.missing_child_edges.values()),
            "complete_pin_table_status": pin_map.get("status"),
            "injected_children": sorted(key for key, value in children.items() if value is not None),
            "missing_children": [key for key in expected_children if children.get(key) is None],
            "verified_edge_candidates": expected_count,
            "bound_verified_edges": sum(len(value) for value in bound_edges.values()),
            "binding_edges": bound_edges,
            "tools": tool_gates(path, module_name),
            "closure": "PENDING_CHILD_BEHAVIORAL_STATUS"}


def direct_tests() -> dict[str, Any]:
    """Run the corresponding parent direct tests. / 运行对应父级 direct test。"""

    scripts = [
        TEST / "Testing-Cpu-Top.UHSCore.Parent-Hardware.py",
        TEST / "Testing-Cpu-Top.UHSC.Roots-Hardware.py",
    ]
    results: dict[str, Any] = {}
    for path in scripts:
        result = subprocess.run([sys.executable, str(path)], capture_output=True, check=False)
        output = (result.stdout + result.stderr).decode("utf-8", "replace")
        results[path.name] = {"status": "PASS" if result.returncode == 0 else "FAIL",
                              "returncode": result.returncode, "output_tail": output[-1200:]}
    return results


def migration_gates() -> dict[str, Any]:
    """Audit product Build structure and keep auxiliary tests stage-only.
    审计 Build 结构，并明确 direct scripts 仍是辅助验证。
    """

    zones = ("Module Contract", "Configuration", "Implementation", "Public Adapter", "Direct Entry")
    forbidden = ("scala", "xstop", "xscore", "source_paths", "source_commit", "provenance", "upstream/")
    builds: dict[str, Any] = {}
    for name in ("roots", "xs_core"):
        path = TARGETS[name]
        text = path.read_text(encoding="utf-8")
        positions = [text.find(zone) for zone in zones]
        has_all = "__all__" in text
        forbidden_terms = [term for term in forbidden if term in text.lower()]
        builds[name] = {"five_zones": positions == sorted(positions) and all(item >= 0 for item in positions),
                        "public_all": has_all, "forbidden_provenance_terms": forbidden_terms,
                        "status": "PASS" if positions == sorted(positions) and all(item >= 0 for item in positions)
                        and has_all and not forbidden_terms else "FAIL"}
    test_paths = {
        "UHSCore": TEST / "Testing-Cpu-Top.UHSCore.Parent-Hardware.py",
        "Roots": TEST / "Testing-Cpu-Top.UHSC.Roots-Hardware.py",
    }
    required_test_markers = ("Module Contract", "Configuration", "Implementation", "Direct Entry",
                             "BuildSubjectContractTest")
    test_files: dict[str, Any] = {}
    for test_name, test_path in test_paths.items():
        test_text = test_path.read_text(encoding="utf-8")
        test_files[test_name] = {
            "path": test_path.relative_to(ROOT).as_posix(),
            "missing_testing_contract_markers": [marker for marker in required_test_markers if marker not in test_text],
            "reads_validation_inventory": "validation/v2-root-port-inventories.json" in test_text,
            "contains_standalone_unittest_main": "unittest.main()" in test_text,
        }
    test_gate = {
        "status": "PENDING",
        "classification": "AUXILIARY_STAGE_TEST_ONLY",
        "files": test_files,
        "reasons": [
            "Both direct scripts need the repository four-section Testing template and BuildSubjectContractTest before migration.",
            "The Roots test reads validation/v2-root-port-inventories.json, so it cannot migrate as a standalone product Testing package.",
        ],
        "formal_testing_migration_required_before_product_acceptance": True,
    }
    return {"build_migration_gate": {
                "status": "PASS_SCOPED_AUDIT" if all(row["status"] == "PASS" for row in builds.values()) else "FAIL",
                "scope": [TARGETS[name].relative_to(ROOT).as_posix() for name in ("roots", "xs_core")],
                "repository_wide_migration_claim": False,
                "files": builds},
            "test_migration_gate": test_gate}


def source_manifest() -> dict[str, Any]:
    """Record all Build, test, and evidence inputs used by this wave. / 记录本波次全部源码与证据输入。"""

    build_files = {
        name: {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
               "sha256": digest(path)}
        for name, path in TARGETS.items()
    }
    test_files = [TEST / "Testing-Cpu-Top.UHSCore.Parent-Hardware.py",
                  TEST / "Testing-Cpu-Top.UHSC.Roots-Hardware.py"]
    validator_path = Path(__file__).resolve()
    evidence_files = [HIERARCHY, INVENTORY, MEM_INVENTORY,
                      ROOT / "validation/backend-port-specs.json"]
    return {
        "build_files": build_files,
        "direct_tests": {path.name: {"path": path.relative_to(ROOT).as_posix(),
                                      "bytes": path.stat().st_size, "sha256": digest(path)}
                         for path in test_files},
        "validator": {"path": validator_path.relative_to(ROOT).as_posix(),
                      "bytes": validator_path.stat().st_size, "sha256": digest(validator_path)},
        "evidence_inputs": {path.name: {"path": path.relative_to(ROOT).as_posix(),
                                        "bytes": path.stat().st_size, "sha256": digest(path)}
                            for path in evidence_files},
    }


def main() -> int:
    """Run the complete bounded wave and emit one dedicated JSON report. / 运行闭环波次并写专属 JSON。"""

    reference = {"path": str(REFERENCE), "bytes": REFERENCE.stat().st_size if REFERENCE.is_file() else None,
                 "sha256": digest(REFERENCE) if REFERENCE.is_file() else None,
                 "expected_bytes": REFERENCE_BYTES, "expected_sha256": REFERENCE_SHA256,
                 "status": "PASS" if REFERENCE.is_file() and REFERENCE.stat().st_size == REFERENCE_BYTES
                 and digest(REFERENCE) == REFERENCE_SHA256 else "FAIL"}
    hierarchy = json.loads(HIERARCHY.read_text(encoding="utf-8"))
    pin_maps = exact_root_pin_maps(hierarchy) if reference["status"] == "PASS" else {}
    modules = {name: load_module(path, f"v2_parent_wave_{name}") for name, path in TARGETS.items()}
    py_compile_results: dict[str, Any] = {}
    for name, path in TARGETS.items():
        result = subprocess.run([sys.executable, "-m", "py_compile", str(path)], capture_output=True, check=False)
        py_compile_results[name] = {"status": "PASS" if result.returncode == 0 else "FAIL",
                                    "returncode": result.returncode}

    inventories = {source: port_rows(source) for source in ("XSCore", "L2Top", "XSTile", "XSTop")}
    inventories["Frontend"] = hierarchy["modules"]["Frontend"]["ports"]
    inventories["Backend"] = hierarchy["modules"]["Backend"]["ports"]
    inventories["MemBlock"] = mem_rows()

    exports: dict[str, Any] = {}
    def capture(name: str, builder: Any, expected_rows: list[dict[str, Any]]) -> None:
        rtl = builder()
        second = builder()
        path, files = write_rtl(name, rtl)
        abi = audit_abi(rtl, name, expected_rows)
        exports[name] = {**files, "expected_ports": len(expected_rows),
                         "generated_ports": header_port_count(rtl, name),
                         "abi_status": abi["status"], "abi": abi,
                         "status": "BOUNDARY",
                         "deterministic": rtl == second,
                         "tools": tool_gates(path, name)}

    # Child parent envelopes are checked independently of root integration.
    capture("Frontend", lambda: modules["frontend"].build_verilog({"module": "Frontend", "locked_io": True}, {}), inventories["Frontend"])
    capture("Backend", lambda: modules["backend"].build_full_verilog({"module": "Backend"}, {}), inventories["Backend"])
    capture("MemBlock", lambda: modules["memblock"].build_verilog({"module": "MemBlock"}, {"full_port_specs": inventories["MemBlock"]}), inventories["MemBlock"])
    for source, product in ROOT_MAP.items():
        capture(product, lambda source=source, product=product: modules["roots"].build_verilog(
            {"root": product, "module": product}, {"full_port_specs": inventories[source]}), inventories[source])

    # Inject the three available child parents using only exact net groups
    # extracted from the locked child instance port lists.
    frontend_child = modules["frontend"].UHSCTop(locked_io=True)
    backend_child = modules["backend"].BackendTop()
    mem_child = modules["memblock"].UHSCMemoryMemBlock(
        injected_dependencies={"full_port_specs": inventories["MemBlock"]})
    core_verified_edges = remap_root_edges(pin_maps.get("XSCore", {}))
    for edge in core_verified_edges:
        for endpoint in [edge["source"], *edge["destinations"]]:
            if endpoint.get("kind") == "child" and endpoint.get("child") == "memBlock":
                endpoint["child"] = "mem_block"
    core_deps = {"full_port_specs": inventories["XSCore"], "frontend": frontend_child,
                 "backend": backend_child, "mem_block": mem_child,
                 "verified_pin_edges": core_verified_edges,
                 "verified_pin_audit": pin_audit(pin_maps["XSCore"])}
    core_target = modules["xs_core"].UHSCoreParent(injected_dependencies=core_deps)
    integrated: dict[str, Any] = {"status": "PENDING", "bound_children": [], "missing_children": []}
    try:
        integrated_rtl = verilog.convert(core_target, name="UHSCoreInjected",
                                         ports=list(core_target.inventory.values()), emit_src=False)
        integrated_second = verilog.convert(core_target, name="UHSCoreInjected",
                                            ports=list(core_target.inventory.values()), emit_src=False)
        path, files = write_rtl("UHSCoreInjected", integrated_rtl)
        core_abi = audit_abi(integrated_rtl, "UHSCoreInjected", inventories["XSCore"])
        integrated = {**files, "status": "BOUNDARY",
                      "bound_children": ["frontend", "backend", "mem_block"],
                      "binding_edges": {key: sorted(value) for key, value in core_target.bound_child_edges.items()},
                      "missing_edges": {key: sorted(value) for key, value in core_target.missing_child_edges.items()},
                      "verified_candidate_edge_count": sum(len(row["destinations"]) for row in core_verified_edges),
                      "bound_verified_edge_count": sum(len(value) for value in core_target.bound_child_edges.values()),
                      "instance_pin_count": pin_maps["XSCore"]["instance_pin_count"],
                      "unsupported_pin_count": pin_maps["XSCore"]["unsupported_pin_count"],
                      "unsupported_pin_counts_by_reason": pin_maps["XSCore"]["unsupported_pin_counts_by_reason"],
                      "verified_edge_missing_count": core_target._verified_unsupported_pin_count + sum(
                          len(rows) for rows in core_target.missing_child_edges.values()),
                      "generated_ports": header_port_count(integrated_rtl, "UHSCoreInjected"),
                      "abi_status": core_abi["status"], "abi": core_abi,
                      "deterministic": integrated_rtl == integrated_second,
                      "tools": tool_gates(path, "UHSCoreInjected"),
                      "closure": "PENDING_CHILD_BEHAVIORAL_STATUS"}
    except Exception as error:
        integrated = {"status": "PENDING", "error": repr(error), "closure": "PENDING_INTEGRATION_TOOL_GATE"}

    def instance_rows(root_name: str) -> list[dict[str, Any]]:
        return list(hierarchy["modules"][root_name]["children"])

    def intbuffer_for(module_name: str, instance_name: str) -> Any:
        if not module_name.startswith("IntBuffer"):
            return None
        return modules["intbuffer"].IntBufferFamily(module_name)

    coupled_parent = modules["coupled_l2"].TL2TLCoupledL2Parent()
    l2_rows = instance_rows("L2Top")
    l2_expected = [str(row["instance"]) for row in l2_rows]
    l2_children = {str(row["instance"]): (coupled_parent if row["instance"] == "inner_l2cache" else None)
                   for row in l2_rows}
    integrated_l2top = integrate_root(
        modules["roots"], "L2Top", modules["roots"].L2Top, inventories["L2Top"],
        l2_expected, l2_children, pin_maps["L2Top"], "L2TopInjected")

    tile_rows = instance_rows("XSTile")
    tile_expected = [str(row["instance"]) for row in tile_rows]
    core_root = modules["roots"].UHSCore(injected_dependencies={
        "full_port_specs": inventories["XSCore"],
        "expected_children": [str(row["instance"]) for row in instance_rows("XSCore")],
    })
    l2_root = modules["roots"].L2Top(injected_dependencies={
        "full_port_specs": inventories["L2Top"], "expected_children": l2_expected,
        "children": l2_children, "verified_pin_edges": remap_root_edges(pin_maps["L2Top"]),
        "verified_pin_audit": pin_audit(pin_maps["L2Top"]),
    })
    tile_children: dict[str, Any] = {}
    for row in tile_rows:
        instance = str(row["instance"])
        module_name = str(row["module"])
        if instance == "core":
            tile_children[instance] = core_root
        elif instance == "l2top":
            tile_children[instance] = l2_root
        else:
            tile_children[instance] = intbuffer_for(module_name, instance)
    integrated_xstile = integrate_root(
        modules["roots"], "XSTile", modules["roots"].UHSTile, inventories["XSTile"],
        tile_expected, tile_children, pin_maps["XSTile"], "UHSTileInjected")

    top_rows = instance_rows("XSTop")
    top_expected = [str(row["instance"]) for row in top_rows]
    top_children: dict[str, Any] = {}
    for row in top_rows:
        instance = str(row["instance"])
        module_name = str(row["module"])
        if instance == "core_with_l2":
            top_children[instance] = modules["roots"].UHSTile(injected_dependencies={
                "full_port_specs": inventories["XSTile"], "expected_children": tile_expected,
                "children": tile_children, "verified_pin_edges": remap_root_edges(pin_maps["XSTile"]),
                "verified_pin_audit": pin_audit(pin_maps["XSTile"]),
            })
        else:
            top_children[instance] = intbuffer_for(module_name, instance)
    integrated_xstop = integrate_root(
        modules["roots"], "XSTop", modules["roots"].UHSCTop, inventories["XSTop"],
        top_expected, top_children, pin_maps["XSTop"], "UHSCTopInjected")

    direct = direct_vectors(modules["xs_core"], modules["roots"], hierarchy)
    tests = direct_tests()
    migration = migration_gates()
    missing_by_root = {
        "XSCore": [],
        "L2Top": integrated_l2top["missing_children"],
        "XSTile": integrated_xstile["missing_children"],
        "XSTop": integrated_xstop["missing_children"],
    }
    bounded_children = {
        "XSCore": ["frontend", "backend", "memBlock"],
        "L2Top": integrated_l2top["injected_children"],
        "XSTile": integrated_xstile["injected_children"],
        "XSTop": integrated_xstop["injected_children"],
    }
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_XSTOP_PARENT_CLOSURE_WAVE",
        "batch_id": "TOP-XSTOP-PARENT-CLOSURE-WAVE-001",
        "source_commit": SOURCE_COMMIT,
        "locked_reference": reference,
        "sources": source_manifest(),
        "hierarchy": {"path": HIERARCHY.relative_to(ROOT).as_posix(),
                      "module_count": hierarchy.get("module_count"),
                      "roots": {root: {"ports": len(inventories[source]),
                                       "direct_children": len(hierarchy["modules"][source]["children"])}
                                for source, root in ROOT_MAP.items()}},
        "exact_pin_maps": pin_maps,
        "py_compile": py_compile_results,
        "exports": exports,
        "integrated_xscore": integrated,
        "integrated_roots": {"L2Top": integrated_l2top, "XSTile": integrated_xstile, "XSTop": integrated_xstop},
        "direct": direct,
        "direct_tests": tests,
        "migration": migration,
        "test_migration_gate": migration["test_migration_gate"],
        "closure": {
            "status": "BOUNDARY" if all(item["abi_status"] == "PASS" for item in exports.values())
            and integrated.get("abi_status") == "PASS"
            and all(item["abi_status"] == "PASS" for item in (integrated_l2top, integrated_xstile, integrated_xstop))
            and direct["status"] == "PASS" else "PENDING",
            "root_status": {"XSCore": "BOUNDARY", "Frontend": "BOUNDARY", "Backend": "BOUNDARY",
                            "MemBlock": "BOUNDARY", "L2Top": "PENDING", "XSTile": "PENDING", "XSTop": "PENDING"},
            "missing_children": missing_by_root,
            "pending_children": bounded_children,
            "reason": "Exact pin tables are extracted from the immutable module spans; behavior stays pending for every bounded or unavailable child.",
        },
        "strict_equivalence": {"count": "43/118", "acceptance_eligible": False},
        "python_line_counts": {
            name: {"current": len(path.read_text(encoding="utf-8").splitlines())}
            for name, path in TARGETS.items()
        },
        "effective_python_lines": sum(len(path.read_text(encoding="utf-8").splitlines())
                                      for path in TARGETS.values()),
        "gates": {"PY_COMPILE": "PASS" if all(v["status"] == "PASS" for v in py_compile_results.values()) else "FAIL",
                  "ABI": "PASS" if all(v["abi_status"] == "PASS" for v in exports.values())
                  and integrated.get("abi_status") == "PASS"
                  and all(v["abi_status"] == "PASS" for v in (integrated_l2top, integrated_xstile, integrated_xstop)) else "FAIL",
                  "DETERMINISTIC_EXPORT": "PASS" if all(v["deterministic"] for v in exports.values())
                  and integrated.get("deterministic", False)
                  and all(v["deterministic"] for v in (integrated_l2top, integrated_xstile, integrated_xstop)) else "FAIL",
                  "DIRECT_PARENT_VECTORS": direct["status"],
                  "BUILD_MIGRATION_GATE": migration["build_migration_gate"]["status"],
                  "TEST_MIGRATION_GATE": migration["test_migration_gate"]["status"],
                  "VERILATOR": "PASS" if all(v["tools"]["verilator"]["status"] == "PASS" for v in exports.values()) else "FAIL",
                  "YOSYS": "PASS" if all(v["tools"]["yosys"]["status"] == "PASS" for v in exports.values()) else "FAIL",
                  "PARENT_CLOSURE": "PENDING_CHILD_BEHAVIORAL_STATUS",
                  "ACCEPTED": "NOT_ALLOWED"},
        "acceptance_eligible": False,
    }
    changed_build_files = ("xs_core", "roots")
    for name in changed_build_files:
        path = TARGETS[name]
        relative = path.relative_to(ROOT).as_posix()
        baseline = subprocess.run(["git", "show", f"HEAD:{relative}"], capture_output=True, check=True).stdout.decode("utf-8")
        current = path.read_text(encoding="utf-8")
        baseline_lines = len(baseline.splitlines())
        current_lines = len(current.splitlines())
        diff = subprocess.run(["git", "diff", "--numstat", "HEAD", "--", relative], capture_output=True, check=True).stdout.decode().strip()
        added, deleted = (int(part) for part in diff.split("\t", 2)[:2])
        payload["python_line_counts"][name].update({"baseline": baseline_lines, "added": added,
                                                    "deleted": deleted, "net_delta": current_lines - baseline_lines})
    payload["implementation_line_delta"] = {
        "files": list(changed_build_files),
        "added": sum(payload["python_line_counts"][name]["added"] for name in changed_build_files),
        "deleted": sum(payload["python_line_counts"][name]["deleted"] for name in changed_build_files),
        "net": sum(payload["python_line_counts"][name]["net_delta"] for name in changed_build_files),
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["closure"]["status"], "output": OUTPUT.as_posix(),
                      "abi": payload["gates"]["ABI"], "direct": direct["status"],
                      "missing": {key: len(value) for key, value in missing_by_root.items()}}, ensure_ascii=False))
    return 0 if payload["closure"]["status"] == "BOUNDARY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
