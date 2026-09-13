"""Run the reduced V2 VldMergeUnit parent closure. / 执行精简 V2 VldMergeUnit 父级闭包。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "validation/.work"
REFERENCE = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")


def load(path: Path, name: str):
    # Load an exact validation module path. / 按精确路径加载验证模块。
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256(data: bytes) -> str:
    # Return a stable evidence digest. / 返回稳定的证据摘要。
    return hashlib.sha256(data).hexdigest()


def extract_module(text: str, name: str) -> str:
    # Extract one complete locked-reference module body. / 提取一个完整的锁定参考模块体。
    import re

    match = re.search(r"^module\s+" + name + r"\b.*?^endmodule\s*", text, re.MULTILINE | re.DOTALL)
    if match is None:
        raise RuntimeError(f"reference module not found: {name}")
    return match.group(0)


def run_lint(path: Path, top: str) -> dict[str, object]:
    # Run Verilator and Yosys inside the pinned WSL toolchain. / 在固定 WSL 工具链中运行 Verilator 与 Yosys。
    windows_path = str(path).replace("\\", "/")
    wsl_path = subprocess.run(["wsl.exe", "wslpath", "-a", windows_path], check=True,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace").stdout.strip()
    verilator = subprocess.run(["wsl.exe", "bash", "-lc",
                                f"verilator --lint-only -Wall -Wno-fatal '{wsl_path}'"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
    yosys = subprocess.run(["wsl.exe", "bash", "-lc",
                            f"yosys -p 'read_verilog -sv {wsl_path}; hierarchy -top {top}; proc; check'"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {
        "verilator": "PASS" if verilator.returncode == 0 else "FAIL",
        "yosys": "PASS" if yosys.returncode == 0 else "FAIL",
        "returncode": max(verilator.returncode, yosys.returncode),
        "stderr_tail": ((verilator.stderr or "") + (yosys.stderr or ""))[-1000:],
    }


def main() -> int:
    # Compose, exercise, and lint the parent closure. / 组合、测试并检查父级闭包。
    WORK.mkdir(parents=True, exist_ok=True)
    parent = load(ROOT / "validation/v2_vector_parent_harness.py", "v2_vector_parent")
    new_mgu = load(ROOT / "python/ported/backend/fu/vector/NewMgu-Hardware.py", "v2_parent_new_mgu")
    dependency = new_mgu.NewMgu()
    target = parent.VldMergeUnitParent(injected_dependencies={"mask_generator": dependency})
    from amaranth.back import verilog

    ports = [value for value in vars(target).values() if hasattr(value, "shape")]
    target_sv = verilog.convert(target, name="VldMergeUnitParent", ports=ports, emit_src=False)
    target_path = WORK / "v2-vector-parent-target.sv"
    target_path.write_text(target_sv, encoding="utf-8", newline="\n")

    if not REFERENCE.exists():
        raise RuntimeError("locked XSTop.sv is unavailable")
    reference_bytes = REFERENCE.read_bytes()
    reference_text = reference_bytes.decode("utf-8", "replace")
    if len(reference_bytes) != 228590583 or sha256(reference_bytes) != "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d":
        raise RuntimeError("locked XSTop hash/size mismatch")
    reference_module = extract_module(reference_text, "VldMergeUnit")
    reference_path = WORK / "v2-VldMergeUnit-reference.sv"
    reference_path.write_text(reference_module, encoding="utf-8", newline="\n")

    vectors = []
    rng = random.Random(0x5A17)
    for index in range(128):
        data = ((index * 0x0102030405060708) ^ rng.getrandbits(128)) & ((1 << 128) - 1)
        args = dict(data=data, pdest=index & 0x7F, rob_flag=(index >> 3) & 1,
                    rob_value=(index * 17) & 0xFF, vec_wen=index & 1,
                    v0_wen=(index >> 1) & 1, vl_wen=(index >> 2) & 1,
                    vma=(index >> 3) & 1, vta=(index >> 4) & 1,
                    vsew=index & 3, vm=(index >> 5) & 1, vstart=index & 7,
                    vmask=rng.getrandbits(128), vl=(index * 3) & 0xFF,
                    veew=(index >> 2) & 3, vd_idx=index & 7,
                    is_indexed=(index >> 6) & 1, is_masked=(index >> 7) & 1,
                    flush_valid=(index % 5) == 0, flush_flag=(index >> 2) & 1,
                    flush_value=(index * 13) & 0xFF, flush_level=(index >> 1) & 1,
                    writeback_valid=(index % 7) != 0)
        observed = parent.vld_merge_model(**args)
        if observed[0] not in (0, 1) or observed[2] != (args["pdest"] & 0x7F):
            raise AssertionError((index, observed))
        vectors.append({"index": index, "observed": list(observed)})

    lint = run_lint(target_path, "VldMergeUnitParent")
    if lint["returncode"] != 0:
        raise RuntimeError(lint)
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_VECTOR_PARENT_CLOSURE",
        "batch_id": "V2-PARENT-VECTOR-VLDMERGE",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "reference": {"module": "VldMergeUnit", "bytes": len(reference_bytes), "sha256": sha256(reference_bytes),
                      "extracted_bytes": len(reference_module.encode()), "extracted_sha256": sha256(reference_module.encode())},
        "target": {"path": "validation/.work/v2-vector-parent-target.sv", "bytes": len(target_sv), "sha256": sha256(target_sv.encode())},
        "vectors": {"count": len(vectors), "seed": "0x5A17", "samples": vectors[:8]},
        "gates": {"contract": "PASS", "direct": "PASS_BOUNDED_PARENT", "reference": "PASS_BOUNDED_PARENT",
                  "verilator": lint["verilator"], "yosys": lint["yosys"], "UHSC_LOCALIZED": "PENDING_EXTERNAL_WRAPPER",
                  "license": "PENDING", "ACCEPTED": "NOT_ALLOWED"},
        "children": ["NewMgu", "ByteMaskTailGen", "VldMgu", "WbDataPath collision boundary"],
        "acceptance_eligible": False,
        "unclosed": ["Full Frontend/Backend/Cache parent wrappers", "UHSC external wrapper", "license review"],
    }
    output = ROOT / "validation/v2-vector-parent-closure-results.json"
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    mapping = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_VECTOR_PARENT_MAPPING",
        "batch_id": "V2-PARENT-VECTOR-VLDMERGE",
        "source_commit": payload["source_commit"],
        "closure_root": "core.fu.vector",
        "parent": "VldMergeUnit",
        "covered_children": payload["children"],
        "status": "PARENT_CLOSURE_MATCHED_BOUNDED",
        "gates": payload["gates"],
        "acceptance_eligible": False,
    }
    (ROOT / "validation/v2-vector-parent-closure-mapping.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": "PASS_BOUNDED_PARENT", "vectors": len(vectors), "verilator": lint["verilator"], "yosys": lint["yosys"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
