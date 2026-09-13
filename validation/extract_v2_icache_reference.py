"""Extract the locked V2 ICache module closures from XSTop.sv.
从锁定的 XSTop.sv 提取 V2 指令缓存模块闭包。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_XSTOP = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
EXPECTED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
EXPECTED_BYTES = 228590583
OUT_DIR = ROOT / "validation/reference-closures"
INDEX = ROOT / "validation/v2-p1-b-icache-reference-index.json"

MODULES = {
    "DeMultiplexer": "DeMultiplexer.sv",
    "DeMultiplexer_1": "DeMultiplexer_1.sv",
    "MuxBundle": "MuxBundle.sv",
    "ICacheMSHR": "ICacheMSHR.sv",
    "ICacheMSHR_4": "ICacheMSHR_4.sv",
    "FIFOReg": "FIFOReg.sv",
    "ICacheReplacer": "ICacheReplacer.sv",
}


# Hash a file without changing line endings. / 在不改变换行的情况下计算文件摘要。
def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Stream one complete Verilog module from the locked artifact.
# 从锁定产物流式提取一个完整 Verilog 模块。
def extract_module(path: Path, name: str) -> tuple[bytes, int, int]:
    start_re = re.compile(rb"^module\s+" + re.escape(name.encode("ascii")) + rb"\s*\(")
    module_re = re.compile(rb"^module\s+")
    end_re = re.compile(rb"^endmodule\b")
    captured: list[bytes] = []
    start_line = 0
    depth = 0
    with path.open("rb") as stream:
        for line_number, line in enumerate(stream, 1):
            if depth == 0:
                if not start_re.match(line):
                    continue
                start_line = line_number
                depth = 1
                captured.append(line)
                continue
            captured.append(line)
            if module_re.match(line):
                depth += 1
            if end_re.match(line):
                depth -= 1
                if depth == 0:
                    return b"".join(captured), start_line, line_number
    raise RuntimeError(f"module {name} not found or not terminated in {path}")


# Validate and extract all independently usable V2 closures. / 校验并提取所有可独立使用的 V2 闭包。
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xstop", type=Path, default=DEFAULT_XSTOP)
    args = parser.parse_args()
    xstop = args.xstop
    if not xstop.is_file():
        raise FileNotFoundError(xstop)
    xstop_size = xstop.stat().st_size
    xstop_sha = digest(xstop)
    if xstop_size != EXPECTED_BYTES or xstop_sha != EXPECTED_SHA256:
        raise RuntimeError(f"locked XSTop mismatch: {xstop_size} {xstop_sha}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for module, filename in MODULES.items():
        payload, first, last = extract_module(xstop, module)
        destination = OUT_DIR / filename
        destination.write_bytes(payload)
        rows.append({
            "module": module,
            "path": destination.relative_to(ROOT).as_posix(),
            "sha256": digest(destination),
            "bytes": len(payload),
            "xstop_line_start": first,
            "xstop_line_end": last,
            "source_scala": (
                "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala"
                if module.startswith(("DeMultiplexer", "MuxBundle", "ICacheMSHR"))
                else "upstream/src/main/scala/xiangshan/frontend/icache/FIFO.scala"
                if module == "FIFOReg"
                else "upstream/src/main/scala/xiangshan/frontend/icache/ICache.scala"
            ),
        })
    payload = {
        "schema_version": 1,
        "kind": "V2_P1_B_ICACHE_REFERENCE_EXTRACTION",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "xstop": {
            "canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
            "local_access_path": str(xstop),
            "sha256": xstop_sha,
            "bytes": xstop_size,
        },
        "modules": rows,
        "extraction": "PASS",
        "locked_input_unchanged": True,
        "acceptance_eligible": False,
    }
    INDEX.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"modules": len(rows), "xstop_sha256": xstop_sha}, sort_keys=True))


if __name__ == "__main__":
    main()
