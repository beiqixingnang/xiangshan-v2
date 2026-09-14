"""Independent probe for the Kunminghu V2 full-generation gate.
昆明湖 V2 完整生成门禁的独立探针。

The probe converts the explicit UHSCTop boundary, inventories the 57 existing
Build-Cpu files, and records which top closures are still absent.  It is
deliberately independent from implementation workers and never promotes a
bounded/reduced result to ``ACCEPTED``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from amaranth.sim import Settle, Simulator


ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "python/Program-System/System-Build/Build-Cpu"
TOP_FILE = BUILD_ROOT / "Cpu-Core/Build-Cpu.Top.UHSCTop-GenerationProbe-Hardware.py"
ROOTS_FILE = BUILD_ROOT / "Cpu-Core/Build-Cpu.Top.XiangShan-Roots-Hardware.py"
WORK_DIR = ROOT / "validation/.work"
RTL_FILE = WORK_DIR / "uhsc-top-probe.sv"
INTEGRATED_RTL_FILE = WORK_DIR / "uhsc-top-integrated-probe.sv"
ROOT_ENVELOPE_RTL_FILE = WORK_DIR / "uhsc-xstop-envelope.sv"
EVIDENCE = ROOT / "validation/v2-top-generation-probe-results.json"
XSTOP_INVENTORY = ROOT / "validation/v2-xstop-port-inventory.json"
ROOT_INVENTORIES = ROOT / "validation/v2-root-port-inventories.json"
EXPECTED_REFERENCE = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
EXPECTED_SOURCE = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"

# Locked XSTop module inventory (named ANSI ports) captured from the pinned
# artifact.  These counts are the target of the eventual full differential;
# the reduced probe deliberately does not claim to match them.
REFERENCE_HIERARCHY = {
    "Frontend": {"ports": 371, "children": ["Ftq", "IBuffer", "ICache", "InstrUncache", "NewIFU", "Predictor", "TLB", "PMP", "PMPChecker_2", "PTWFilter", "PTWRepeaterNB"]},
    "Backend": {"ports": 1165, "children": ["BypassNetwork", "CtrlBlock", "DataPath", "ExuBlock", "Scheduler", "WbDataPath", "WbFuBusyTable", "Og2ForVector", "VecExcpDataMergeModule"]},
    "MemBlock": {"ports": 1326, "children": ["DCacheWrapper", "AtomicsUnit", "LoadUnit", "StoreUnit", "LsqWrapper", "L2TLBWrapper", "FrontendBridge", "Uncache", "TLXbar_6", "TLBuffer_20", "TLBuffer_21", "TLBuffer_22", "TLBuffer_23"]},
    "XSCore": {"ports": 308, "children": ["Frontend", "Backend", "MemBlock"]},
    "L2Top": {"ports": 441, "children": ["TL2TLCoupledL2", "BusErrorUnit", "TLClientsMerger_1", "TLXbar_7", "TLXbar_8", "TLXbar_9"]},
    "XSTile": {"ports": 153, "children": ["XSCore", "L2Top", "IntBuffer", "IntBuffer_1", "IntBuffer_2"]},
    "XSTop": {"ports": 204, "children": ["XSTile", "HuanCun", "SoCMisc", "ResetGen", "TLToAXI4_2", "AXI4Map", "imsic_bus_top"]},
}


def load_top_module():
    """Load the hyphenated Build file without changing its source imports.
    以不修改源文件导入的方式加载带连字符的 Build 文件。
    """

    spec = importlib.util.spec_from_file_location("uhsc_top_probe", TOP_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {TOP_FILE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_module(path: Path, name: str):
    """Load one sibling Build file for validator-only dependency injection.
    仅供 validator 注入依赖时加载一个相邻 Build 文件。
    """

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def module_names(text: str) -> list[str]:
    """Return deterministic Verilog module names from generated text.
    从生成文本中提取确定性的 Verilog 模块名。
    """

    names = re.findall(r"^module\s+(?:\\)?([A-Za-z_][A-Za-z0-9_$.]*)\s*\(", text, re.MULTILINE)
    return sorted(set(names))


def generated_port_schema(text: str, module_name: str) -> dict[str, tuple[str, int]]:
    """Read one generated module's ANSI direction/width declarations."""
    start = text.index(f"module {module_name}(")
    end = text.index("endmodule", start)
    result: dict[str, tuple[str, int]] = {}
    for line in text[start:end].splitlines():
        match = re.match(r"\s*(input|output|inout)(?:\s+\[(\d+):0\])?\s+(.+);\s*$", line)
        if match is None:
            continue
        direction, high, names = match.groups()
        width = int(high) + 1 if high is not None else 1
        for name in names.split(","):
            clean = name.strip().replace("\\", "").strip()
            if clean:
                result[clean] = (direction, width)
    return result


def inventory_schema(specs: list[dict[str, object]]) -> dict[str, tuple[str, int]]:
    """Normalize frozen inventory rows for exact structural comparison."""
    result: dict[str, tuple[str, int]] = {}
    for spec in specs:
        name = str(spec.get("name", ""))
        if not name:
            continue
        raw_width = str(spec.get("width", "")).strip()
        width = 1
        if raw_width.startswith("[") and raw_width.endswith("]") and ":" in raw_width:
            high, low = raw_width[1:-1].split(":", 1)
            try:
                width = abs(int(high) - int(low)) + 1
            except ValueError:
                width = 1
        result[name] = (str(spec.get("direction", "input")).lower(), max(1, width))
    return result


def run_lint(tool: str, rtl_path: Path, top_name: str = "UHSCTopIntegratedProbe") -> str:
    """Run a host or WSL lint tool, preserving unavailable as an explicit state.
    在主机或 WSL 中运行 lint 工具；不可用时明确记录 UNAVAILABLE。
    """

    host = shutil.which(tool)
    if host:
        if tool == "verilator":
            command = [host, "--lint-only", "--Wno-fatal", str(rtl_path)]
        else:
            command = [host, "-p", f"read_verilog -sv {rtl_path}; hierarchy -check -top {top_name}"]
        return "PASS" if subprocess.run(command, capture_output=True, check=False).returncode == 0 else "FAIL"
    wsl = shutil.which("wsl.exe")
    if not wsl:
        return "UNAVAILABLE"
    posix_path = str(rtl_path.resolve()).replace("\\", "/")
    if len(posix_path) >= 2 and posix_path[1] == ":":
        posix_path = "/mnt/" + posix_path[0].lower() + posix_path[2:]
    if tool == "verilator":
        shell = f"verilator --lint-only --Wno-fatal '{posix_path}'"
    else:
        shell = f"yosys -p 'read_verilog -sv \"{posix_path}\"; hierarchy -check -top {top_name}'"
    result = subprocess.run([wsl, "-e", "bash", "-lc", shell], capture_output=True, check=False)
    return "PASS" if result.returncode == 0 else "FAIL"


def main() -> int:
    builds = sorted(BUILD_ROOT.rglob("Build-*.py"))
    top = load_top_module()
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    rtl = top.build_verilog()
    RTL_FILE.write_text(rtl, encoding="utf-8", newline="\n")
    modules = module_names(rtl)

    # Validator-only integration: load the existing reduced parent/family
    # targets and inject them into UHSCTop.  The Build file itself remains free
    # of sibling imports, while this check proves that one hierarchy can
    # elaborate through the current closure boundaries.
    frontend_mod = load_module(BUILD_ROOT / "Cpu-Core/Build-Cpu.Frontend.Top-Hardware.py", "v2_frontend_top")
    backend_mod = load_module(BUILD_ROOT / "Cpu-Core/Build-Cpu.Backend.Top-Hardware.py", "v2_backend_top")
    mem_mod = load_module(BUILD_ROOT / "Cpu-Memory/Build-Cpu.Memory.MemBlock-Hardware.py", "v2_memblock")
    l2_mod = load_module(BUILD_ROOT / "Cpu-Memory/Build-Cpu.Dependency.CoupledL2.Slice-Hardware.py", "v2_coupled_l2")
    roots_mod = load_module(BUILD_ROOT / "Cpu-Core/Build-Cpu.Top.XiangShan-Roots-Hardware.py", "v2_roots")
    deps = {
        "frontend": frontend_mod.FrontendParent(),
        "backend": backend_mod.BackendTop(),
        "mem_block": mem_mod.UHSCMemoryMemBlock(),
        "coupled_l2": l2_mod.CoupledL2Slice(),
    }
    integrated_rtl = top.build_verilog({"module": "UHSCTopIntegratedProbe"}, deps)
    INTEGRATED_RTL_FILE.write_text(integrated_rtl, encoding="utf-8", newline="\n")
    integrated_modules = module_names(integrated_rtl)

    # Generate the exact parent envelopes independently before attempting the
    # top-level bind.  This keeps the structural gate honest: each envelope
    # must elaborate from versioned inventory metadata, while the integrated
    # hierarchy remains explicitly reduced until child behavior is complete.
    backend_specs_path = ROOT / "validation/backend-port-specs.json"
    mem_specs_path = ROOT / "validation/v2-memblock-port-inventory.json"
    full_parent_envelopes: dict[str, object] = {}
    if backend_specs_path.is_file():
        backend_specs = json.loads(backend_specs_path.read_text(encoding="utf-8"))["ports"]
        backend_full = backend_mod.build_full_verilog({"module": "UHSCBackendEnvelope"}, {})
        backend_path = WORK_DIR / "uhsc-backend-envelope.sv"
        backend_path.write_text(backend_full, encoding="utf-8", newline="\n")
        full_parent_envelopes["Backend"] = {
            "inventory_count": len(backend_specs),
            "generated_ports": len(backend_mod.full_backend_port_schema()),
            "rtl_bytes": len(backend_full.encode("utf-8")),
            "rtl_sha256": hashlib.sha256(backend_full.encode("utf-8")).hexdigest(),
            "path": str(backend_path.relative_to(ROOT)).replace("\\", "/"),
        }
    if mem_specs_path.is_file():
        mem_payload = json.loads(mem_specs_path.read_text(encoding="utf-8"))
        mem_specs = mem_payload.get("ports", [])
        mem_full = mem_mod.build_verilog({"module": "UHSCMemBlockEnvelope"}, {"full_port_specs": mem_specs})
        mem_path = WORK_DIR / "uhsc-memblock-envelope.sv"
        mem_path.write_text(mem_full, encoding="utf-8", newline="\n")
        full_parent_envelopes["MemBlock"] = {
            "inventory_count": len(mem_specs),
            "rtl_bytes": len(mem_full.encode("utf-8")),
            "rtl_sha256": hashlib.sha256(mem_full.encode("utf-8")).hexdigest(),
            "path": str(mem_path.relative_to(ROOT)).replace("\\", "/"),
        }
    # Pass exact root inventories as explicit metadata to the source-named
    # root adapter; no root target reads these files.
    root_specs_by_name: dict[str, list[dict[str, object]]] = {}
    if ROOT_INVENTORIES.is_file():
        root_payload = json.loads(ROOT_INVENTORIES.read_text(encoding="utf-8"))
        if (root_payload.get("source_commit") != EXPECTED_SOURCE
                or root_payload.get("reference_sha256") != EXPECTED_REFERENCE):
            raise RuntimeError("root inventory baseline mismatch")
        for name, metadata in root_payload.get("modules", {}).items():
            ports = metadata.get("ports", []) if isinstance(metadata, dict) else []
            if name in {"XSCore", "L2Top", "XSTile", "XSTop"} and isinstance(ports, list):
                root_specs_by_name[name] = ports
    # Cross-check the separately versioned XSTop inventory against the root
    # inventory bundle;
    # a mismatch is a hard structural failure rather than silently choosing a
    # different snapshot.
    if XSTOP_INVENTORY.is_file():
        xstop_payload = json.loads(XSTOP_INVENTORY.read_text(encoding="utf-8"))
        if (xstop_payload.get("source_commit") != EXPECTED_SOURCE
                or xstop_payload.get("reference_sha256") != EXPECTED_REFERENCE):
            raise RuntimeError("XSTop inventory baseline mismatch")
        xstop_specs = xstop_payload.get("ports", [])
        if xstop_payload.get("module") != "XSTop" or len(xstop_specs) != 204:
            raise RuntimeError("XSTop inventory schema/count mismatch")
        if "XSTop" in root_specs_by_name and root_specs_by_name["XSTop"] != xstop_specs:
            raise RuntimeError("XSTop inventory disagrees with root inventory bundle")
        root_specs_by_name["XSTop"] = xstop_specs
    root_types = ("XSCore", "L2Top", "XSTile", "XSTop")
    for root_name in root_types:
        root_specs = root_specs_by_name.get(root_name)
        if root_specs is None:
            # Keep absent root inventories explicit instead of inventing port
            # names; a later root-closure batch can supply them through the
            # same metadata channel.
            full_parent_envelopes[root_name] = {
                "inventory_count": 0,
                "generated_ports": 0,
                "status": "PENDING_ROOT_INVENTORY",
            }
            continue
        module_name = f"UHSC{root_name}Envelope"
        root_full = roots_mod.build_verilog(
            {"root": root_name, "module": module_name},
            {"full_port_specs": root_specs},
        )
        root_path = WORK_DIR / f"uhsc-{root_name.lower()}-envelope.sv"
        root_path.write_text(root_full, encoding="utf-8", newline="\n")
        root_actual = generated_port_schema(root_full, module_name)
        root_expected = inventory_schema(root_specs)
        root_missing = sorted(set(root_expected) - set(root_actual))
        root_extra = sorted(set(root_actual) - set(root_expected))
        root_mismatches = [name for name in sorted(set(root_expected) & set(root_actual))
                           if root_expected[name] != root_actual[name]]
        root_verilator = run_lint("verilator", root_path, module_name)
        root_yosys = run_lint("yosys", root_path, module_name)
        full_parent_envelopes[root_name] = {
            "inventory_count": len(root_specs),
            "generated_ports": len(root_actual),
            "missing": root_missing,
            "extra": root_extra,
            "direction_width_mismatches": root_mismatches,
            "rtl_bytes": len(root_full.encode("utf-8")),
            "rtl_sha256": hashlib.sha256(root_full.encode("utf-8")).hexdigest(),
            "path": str(root_path.relative_to(ROOT)).replace("\\", "/"),
            "status": "PASS" if len(root_actual) == len(root_expected) == len(root_specs)
            and not root_missing and not root_extra and not root_mismatches else "FAIL",
            "verilator": root_verilator,
            "yosys": root_yosys,
        }
    frontend_full = frontend_mod.build_verilog({"module": "UHSCFrontendEnvelope", "locked_io": True}, {})
    frontend_path = WORK_DIR / "uhsc-frontend-envelope.sv"
    frontend_path.write_text(frontend_full, encoding="utf-8", newline="\n")
    full_parent_envelopes["Frontend"] = {
        "inventory_count": len(frontend_mod.frontend_port_specs()),
        "rtl_bytes": len(frontend_full.encode("utf-8")),
        "rtl_sha256": hashlib.sha256(frontend_full.encode("utf-8")).hexdigest(),
        "path": str(frontend_path.relative_to(ROOT)).replace("\\", "/"),
    }

    # Direct quiescent-probe contract: no injected closures must advertise
    # four missing hierarchy roots and never claim completion.
    direct_top = top.UHSCTop()
    sim = Simulator(direct_top)
    direct_observed: dict[str, int] = {}

    def sample_direct():
        yield direct_top.reset.eq(1)
        yield Settle()
        direct_observed.update({
            "closure_missing": (yield direct_top.closure_missing),
            "closure_missing_count": (yield direct_top.closure_missing_count),
            "closure_complete": (yield direct_top.closure_complete),
            "cpu_halted": (yield direct_top.cpu_halted),
        })

    sim.add_process(sample_direct)
    sim.run()

    # These are the mandatory V2 hierarchy roots identified from Top.scala.
    required_roots = ["XSCore", "L2Top", "XSTile", "XSTop"]
    present_build_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in builds)
    defined_classes = set(re.findall(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\b", present_build_text, re.MULTILINE))
    # Match actual class definitions, not prose/docstrings that mention the
    # names of still-unimplemented Scala roots.
    missing_build_roots = [root for root in required_roots if root not in defined_classes]
    reduced_boundary_roots = [root for root in required_roots if root in defined_classes]
    generated_top = "UHSCTop" in modules

    verilator_status = run_lint("verilator", INTEGRATED_RTL_FILE)
    yosys_status = run_lint("yosys", INTEGRATED_RTL_FILE)

    report = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_TOP_GENERATION_PROBE",
        "status": "GENERATION_PROBE_PASS_REDUCED" if generated_top else "GENERATION_PROBE_FAIL",
        "complete_gate": "BLOCKED_MISSING_CLOSURES",
        "accepted": "NOT_ALLOWED",
        "build_file_count": len(builds),
        "build_files": [str(path.relative_to(ROOT)).replace("\\", "/") for path in builds],
        "generated_artifact": {
            "path": str(RTL_FILE.relative_to(ROOT)).replace("\\", "/"),
            "sha256": hashlib.sha256(rtl.encode("utf-8")).hexdigest(),
            "bytes": len(rtl.encode("utf-8")),
            "modules": modules,
            "top_module": "UHSCTop" if generated_top else None,
        },
        "integrated_reduced_hierarchy": {
            "path": str(INTEGRATED_RTL_FILE.relative_to(ROOT)).replace("\\", "/"),
            "sha256": hashlib.sha256(integrated_rtl.encode("utf-8")).hexdigest(),
            "bytes": len(integrated_rtl.encode("utf-8")),
            "modules": integrated_modules,
            "bound_children": sorted(deps),
            "status": "ELABORATED_REDUCED_ONLY",
        },
        "full_parent_envelopes": full_parent_envelopes,
        "direct_probe_observation": direct_observed,
        "required_hierarchy_roots": required_roots,
        "locked_reference_hierarchy": REFERENCE_HIERARCHY,
        "defined_build_classes": sorted(name for name in defined_classes if name in required_roots),
        "missing_build_roots": missing_build_roots,
        "reduced_boundary_roots": reduced_boundary_roots,
        "locked_baseline": {
            "source_commit": EXPECTED_SOURCE,
            "reference_xstop_sha256": EXPECTED_REFERENCE,
            "reference_immutable": True,
        },
        "tool_gates": {
            "verilator_lint": verilator_status,
            "yosys_integrated_hierarchy": yosys_status,
            "root_envelope_verilator": {
                name: full_parent_envelopes[name].get("verilator", "PENDING")
                for name in required_roots
            },
            "root_envelope_yosys": {
                name: full_parent_envelopes[name].get("yosys", "PENDING")
                for name in required_roots
            },
        },
        "blocking_reasons": [
            "source-named XSCore/L2Top/XSTile/XSTop roots are reduced boundaries, not complete closures",
            "probe drives quiescent outputs and asserts io_closure_missing",
            "complete XSTop module/port inventory differential has not run",
        ],
    }
    EVIDENCE.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    # A generated probe is useful evidence even when an optional host linter is
    # unavailable; the complete gate remains blocked by the missing closures.
    return 0 if generated_top and verilator_status in {"PASS", "UNAVAILABLE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
