"""Rebind selected member receipts only after byte-identical RTL exports.

Original execution sources and proof logs stay intact. This is a focused
identity gate for the current Decode and MMU/LSQ receipts, not a proof of any
additional member or a change to the strict Build numerator.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from v2_strict_family_rail import export_member, load_module


ROOT = Path(__file__).resolve().parents[1]
RECORDS = (
    ("validation/v2-backend-closure-wave-uopinfo.json", "UopInfoGen", "wave"),
    ("validation/v2-uopinfo-packed-reference-proof.json", "UopInfoGen", "packed"),
    ("validation/v2-memblock-closure-wave-age38.json", "AgeDetector_38", "mmu"),
    ("validation/v2-memblock-closure-wave-bitmap.json", "Bitmap", "mmu"),
)


def checksum(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    pending = []
    modules = {}
    for relative, member, kind in RECORDS:
        path = ROOT / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        if kind == "wave":
            build_path = payload["build_path"]
            expected = payload["export"]["sha256"]
            before = payload["build_sha256"]
        elif kind == "packed":
            build_path = payload["sources"]["build"]["path"]
            expected = payload["prepared"]["prepared_hashes"]["target"]
            before = payload["sources"]["build"]["sha256"]
        else:
            build_path = payload["build"]["path"]
            expected = payload["build"]["verilog_sha256"]
            before = payload["build"]["sha256"]
        source = ROOT / build_path
        if build_path not in modules:
            modules[build_path] = load_module("representation_" + member, source)
        module = modules[build_path]
        rtl = (export_member(module, member) if kind == "packed"
               else module.build_verilog({"module": member}, {}))
        observed = checksum(rtl.encode("utf-8"))
        if observed != expected:
            raise AssertionError(f"{relative}: generated RTL changed; a fresh proof is required")
        current = checksum(source.read_bytes())
        record = {
            "previous_build_sha256": before, "current_build_sha256": current,
            "member": member, "expected_rtl_sha256": expected,
            "current_rtl_sha256": observed, "rtl_byte_identical": True,
            "producer": Path(__file__).relative_to(ROOT).as_posix(),
            "producer_sha256": checksum(Path(__file__).read_bytes()),
            "strict_build_count_delta": 0,
        }
        payload.setdefault("representation_rebindings", []).append(record)
        if kind == "wave":
            payload.setdefault("original_execution_build_sha256", before)
            payload["build_sha256"] = current
        elif kind == "packed":
            payload.setdefault("original_execution_sources", payload["sources"].copy())
            payload["sources"]["build"] = {"path": build_path, "sha256": current,
                                              "bytes": source.stat().st_size}
        else:
            payload.setdefault("original_execution_build", payload["build"].copy())
            payload["build"]["sha256"] = current
        pending.append((path, payload))
    # Check all records before mutating any evidence file.
    for path, payload in pending:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    result = {"status": "PASS_RTL_IDENTITY_NON_COUNTING", "records": len(pending),
              "strict_build_count_delta": 0,
              "bindings": [payload["representation_rebindings"][-1] for _, payload in pending]}
    (ROOT / "validation/v2-closure-representation-rebind-results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": result["status"], "records": len(pending)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
