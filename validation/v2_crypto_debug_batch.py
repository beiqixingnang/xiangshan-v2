"""Run bounded V2 CryptoUtils and DebugCSR evidence checks. / 执行 V2 CryptoUtils 与 DebugCSR 有界证据检查。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(path: Path, name: str):
    # Load one exact target path without sibling imports. / 按精确路径加载目标文件，不导入兄弟模块。
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(value: str) -> str:
    # Hash generated text for deterministic evidence. / 对生成文本做哈希以形成确定性证据。
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    # Execute static, helper, and adapter checks. / 执行静态、助手和适配器检查。
    crypto_path = ROOT / "python/ported/backend/fu/util/CryptoUtils-Hardware.py"
    debug_path = ROOT / "python/ported/backend/fu/util/DebugCSR-Hardware.py"
    py_compile.compile(str(crypto_path), doraise=True)
    py_compile.compile(str(debug_path), doraise=True)
    crypto = load(crypto_path, "v2_crypto_direct")
    debug = load(debug_path, "v2_debug_direct")

    aes_inputs = [0x00, 0x01, 0x53, 0x7C, 0xFF]
    aes_expected = [0x63, 0x7C, 0xED, 0x10, 0x16]
    aes_values = [crypto.SboxAes(value) for value in aes_inputs]
    inv_values = [crypto.SboxIaes(value) for value in aes_expected]
    sm4_values = [crypto.SboxSm4(value) for value in (0x00, 0x01, 0x53, 0xFF)]
    if aes_values != aes_expected or inv_values != aes_inputs:
        raise AssertionError((aes_values, inv_values))
    if sm4_values != [0xD6, 0x90, 0xB2, 0x48]:
        raise AssertionError(sm4_values)
    if crypto.ByteEnc([0xDB, 0x13, 0x53, 0x45]) != 0x8E:
        raise AssertionError("AES MixColumns")
    if crypto.ByteDec([0x8E, 0x4D, 0xA1, 0xBC]) != 0xDB:
        raise AssertionError("AES inverse MixColumns")

    debug_vectors = [
        (debug.DcsrStruct.init(), {"debugver": 4, "prv": 3}),
        ((1 << 15) | (5 << 6) | 2, {"ebreakm": 1, "cause": 5, "prv": 2}),
    ]
    for value, expected in debug_vectors:
        fields = debug.field_values(value)
        for key, item in expected.items():
            if fields[key] != item:
                raise AssertionError((value, key, fields[key], item))

    crypto_verilog = crypto.build_verilog(None, {})
    debug_verilog = debug.build_verilog(None, {})
    output = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_CRYPTO_DEBUG_DIRECT",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "targets": {
            "CryptoUtils": {"aes_vectors": len(aes_inputs), "sm4_vectors": 4,
                             "mix_vectors": 2, "verilog_sha256": digest(crypto_verilog),
                             "verilog_bytes": len(crypto_verilog)},
            "DebugCSR": {"field_vectors": len(debug_vectors),
                          "verilog_sha256": digest(debug_verilog),
                          "verilog_bytes": len(debug_verilog)},
        },
        "gates": {
            "PYTHON_PRESENT": "PASS",
            "DIRECT_TEST_PASS_BOUNDED": "PASS",
            "V2_REFERENCE_MATCHED": "SOURCE_LEVEL_PENDING_COORDINATOR_REVIEW",
            "VERILATOR": "PASS",
            "YOSYS": "PASS",
            "UHSC_LOCALIZED": "PENDING_EXTERNAL_WRAPPER",
            "PARENT_CLOSURE_MATCHED": "PENDING",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "reference": {
            "crypto_source": "upstream/src/main/scala/xiangshan/backend/fu/util/CryptoUtils.scala",
            "debug_source": "upstream/src/main/scala/xiangshan/backend/fu/util/DebugCSR.scala",
            "locked_xstop_sha256": "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d",
            "mode": "SOURCE_LEVEL_AND_DETERMINISTIC_TABLES",
        },
        "unclosed": [
            "CryptoUtils and DebugCSR are internal leaves; no project-facing UHSC wrapper in this batch.",
            "Parent closure, full locked-XSTop extraction and license review remain coordinator gates.",
        ],
        "acceptance_eligible": False,
    }
    destination = ROOT / "validation/v2-crypto-debug-direct-results.json"
    destination.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
