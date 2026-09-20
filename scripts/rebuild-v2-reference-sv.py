"""Rebuild the ignored per-module V2 reference SystemVerilog directory.

The complete locked ``XSTop.sv`` is generated from the vendored Kunminghu V2
sources and is intentionally too large to track. This utility verifies that
artifact by SHA-256, then reproduces the 1976 exact module slices described by
the tracked hierarchy inventory. It never edits the generated source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HIERARCHY = ROOT / "validation/v2-locked-hierarchy.json"
DEFAULT_OUTPUT = ROOT / "validation/reference-sv"
EXPECTED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
EXPECTED_MODULES = 1976


def sha256(path: Path) -> str:
    """Return the SHA-256 digest of one file. / 返回单个文件的 SHA-256。"""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_inventory() -> dict[str, Any]:
    """Load and validate the tracked hierarchy inventory. / 加载并校验层次清单。"""

    payload = json.loads(HIERARCHY.read_text(encoding="utf-8"))
    modules = payload.get("modules")
    if payload.get("reference_sha256") != EXPECTED_SHA256:
        raise ValueError("hierarchy inventory reference hash changed")
    if payload.get("module_count") != EXPECTED_MODULES or not isinstance(modules, dict):
        raise ValueError("hierarchy inventory module count changed")
    if len(modules) != EXPECTED_MODULES:
        raise ValueError("hierarchy inventory module table is incomplete")
    return modules


def module_slice(lines: list[bytes], name: str, record: dict[str, Any]) -> bytes:
    """Extract one inventory-defined module without rewriting bytes. / 按清单提取模块原始字节。"""

    first = int(record["start_line"])
    last = int(record["end_line"])
    if first < 1 or last < first or last > len(lines):
        raise ValueError(f"{name}: invalid line interval {first}:{last}")
    payload = b"".join(lines[first - 1:last])
    header = re.search(rb"(?m)^module\s+([A-Za-z_][A-Za-z0-9_$]*)\s*\(", payload)
    if header is None or header.group(1).decode("ascii") != name:
        raise ValueError(f"{name}: module header does not match the inventory")
    if not re.search(rb"(?m)^endmodule\b", payload):
        raise ValueError(f"{name}: extracted module is unterminated")
    return payload


def rebuild(xstop: Path, output: Path, verify_only: bool) -> dict[str, Any]:
    """Rebuild or verify every exact module slice. / 重建或核验所有精确模块切片。"""

    observed_hash = sha256(xstop)
    if observed_hash != EXPECTED_SHA256:
        raise ValueError(f"locked XSTop hash mismatch: {observed_hash}")
    modules = load_inventory()
    lines = xstop.read_bytes().splitlines(keepends=True)
    if not verify_only:
        output.mkdir(parents=True, exist_ok=True)
    mismatched: list[str] = []
    written = 0
    for name, raw_record in modules.items():
        if not isinstance(raw_record, dict):
            raise TypeError(f"{name}: hierarchy record is not an object")
        payload = module_slice(lines, str(name), raw_record)
        target = output / f"{name}.sv"
        if verify_only:
            if not target.is_file() or target.read_bytes() != payload:
                mismatched.append(str(name))
        else:
            target.write_bytes(payload)
            written += 1
    expected_names = {f"{name}.sv" for name in modules}
    unexpected = sorted(path.name for path in output.glob("*.sv") if path.name not in expected_names)
    status = "PASS" if not mismatched and not unexpected else "FAIL"
    return {
        "status": status,
        "xstop_sha256": observed_hash,
        "module_count": len(modules),
        "written": written,
        "verified": len(modules) - len(mismatched),
        "mismatched": mismatched,
        "unexpected": unexpected,
        "output": str(output),
    }


def main() -> int:
    """Parse arguments and run the deterministic rebuild. / 解析参数并执行确定性重建。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xstop", required=True, type=Path, help="complete generated XSTop.sv")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    result = rebuild(arguments.xstop.resolve(), arguments.output.resolve(), arguments.verify_only)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
