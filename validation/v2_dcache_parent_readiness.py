"""Index the locked V2 DCache parent boundaries. / 索引锁定 V2 数据缓存父级边界。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
EXPECTED_SHA = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
EXPECTED_BYTES = 228590583
SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
OUTPUT = ROOT / "validation/v2-dcache-parent-readiness.json"


def sha256(data: bytes) -> str:
    # Return an immutable input digest. / 返回不可变输入摘要。
    return hashlib.sha256(data).hexdigest()


def extract_module(text: str, name: str) -> tuple[int, int, str]:
    # Extract one complete SystemVerilog module and its line span. / 提取完整 SystemVerilog 模块及行范围。
    match = re.search(r"^module\s+" + re.escape(name) + r"\b.*?^endmodule\s*", text, re.MULTILINE | re.DOTALL)
    if match is None:
        raise RuntimeError(f"missing module {name}")
    start = text.count("\n", 0, match.start()) + 1
    end = text.count("\n", 0, match.end())
    return start, end, match.group(0)


def port_count(module: str) -> int:
    # Count declared input/output/inout tokens in a flattened generated module. / 统计扁平生成模块的端口声明。
    return len(re.findall(r"\b(?:input|output|inout)\b", module))


def main() -> int:
    # Build parent boundary metadata without changing source or product code. / 构建父级边界元数据，不修改源代码或产品代码。
    raw = REFERENCE.read_bytes()
    if len(raw) != EXPECTED_BYTES or sha256(raw) != EXPECTED_SHA:
        raise RuntimeError("locked XSTop hash/size mismatch")
    text = raw.decode("utf-8", "replace")
    boundaries = []
    for name, source, children, next_action in (
        ("MainPipe", "upstream/src/main/scala/xiangshan/cache/dcache/mainpipe/MainPipe.scala",
         ["AMOALU", "TagArray", "MainPipe"], "Bind AMOALU and TagArray through explicit transaction stubs."),
        ("DCache", "upstream/src/main/scala/xiangshan/cache/dcache/DCacheWrapper.scala",
         ["MainPipe", "TagArray", "AMOALU", "TreeArbiter", "MissReadyGen"], "Add request/miss/refill parent observations after MainPipe."),
        ("DCacheWrapper", "upstream/src/main/scala/xiangshan/cache/dcache/DCacheWrapper.scala",
         ["DCache", "TLBundleA", "TLBundleD", "Mbist"], "Keep TileLink and MBIST/DFT dependencies injected."),
        ("MemBlock", "upstream/src/main/scala/xiangshan/mem/MemBlock.scala",
         ["DCacheWrapper", "ICache", "MMU", "LSU"], "Defer full MemBlock until DCache and ICache contracts are complete."),
    ):
        start, end, body = extract_module(text, name)
        boundaries.append({
            "module": name,
            "source": source,
            "xstop_lines": [start, end],
            "ports": port_count(body),
            "bytes": len(body.encode("utf-8")),
            "sha256": sha256(body.encode("utf-8")),
            "covered_children": children,
            "status": "BOUNDARY_INDEXED",
            "next_action": next_action,
        })
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_DCACHE_PARENT_READINESS",
        "source_commit": SOURCE_COMMIT,
        "reference": {"path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv", "sha256": sha256(raw), "bytes": len(raw), "locked_input_unchanged": True},
        "boundaries": boundaries,
        "existing_leaf_evidence": {
            "AMOALU": "validation/v2-dcache-batch-differential-results.json",
            "TagArray": "validation/v2-dcache-batch-differential-results.json",
        },
        "gates": {
            "PYTHON_PRESENT": "PASS",
            "DIRECT_TEST_PASS_BOUNDED": "PRESENT_LEAVES",
            "V2_REFERENCE_MATCHED": "PRESENT_LEAVES",
            "PARENT_CLOSURE_MATCHED": "PENDING_REDUCED_MAINPIPE_HARNESS",
            "UHSC_LOCALIZED": "PENDING_EXTERNAL_WRAPPER",
            "LICENSE_REVIEW": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "blockers": [
            "MainPipe/DCache/DCacheWrapper/MemBlock are large parent boundaries; leaf evidence is not full-parent equivalence.",
            "TileLink, MBIST/DFT, MMU, LSU, and refill/miss dependencies require explicit injected contracts.",
        ],
        "acceptance_eligible": False,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"boundaries": len(boundaries), "ports": {item["module"]: item["ports"] for item in boundaries}, "status": "PASS", "accepted": "NOT_ALLOWED"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
