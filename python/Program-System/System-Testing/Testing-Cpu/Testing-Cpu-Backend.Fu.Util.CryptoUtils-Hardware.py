#!/usr/bin/env python3
"""Bounded direct checks for the V2 CryptoUtils helper Build.

The vectors exercise the source-level Boolean/GF implementation and its
combinational probe.  They provide bounded source evidence only; no locked
standalone reference is available for this helper.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

from amaranth.sim import Settle, Simulator


ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / (
    "python/Program-System/System-Build/Build-Cpu/Cpu-Core/"
    "Cpu-Core-Backend.Fu.Util.CryptoUtils-Hardware.py"
)


def load_subject() -> Any:
    """Load the exact CryptoUtils Build file by path."""

    spec = importlib.util.spec_from_file_location(
        "testing_v2_crypto_utils_target", TARGET
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {TARGET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CryptoUtilsDirectTest(unittest.TestCase):
    """Check explicit AES/SM4, GF, permutation, and rotation vectors."""

    def test_source_vectors(self) -> None:
        module = load_subject()

        # Standard AES forward/inverse S-box points and SM4 S-box probes.
        self.assertEqual(0xED, module.SboxAes(0x53))
        self.assertEqual(0x50, module.SboxIaes(0x53))
        self.assertEqual(0x53, module.SboxIaes(module.SboxAes(0x53)))
        self.assertEqual(0xD6, module.SboxSm4(0x00))
        self.assertEqual(0x90, module.SboxSm4(0x01))
        self.assertEqual(0xB2, module.SboxSm4(0x53))

        # AES GF(2^8) and MixColumns known-answer vectors.
        self.assertEqual(0xAE, module.Xt2(0x57))
        self.assertEqual(0x77, module.XtN(0x57, 0x0B))
        self.assertEqual(0x04, module.ByteEnc([0xD4, 0xBF, 0x5D, 0x30]))
        self.assertEqual(0xD4, module.ByteDec([0x04, 0x66, 0x81, 0xE5]))
        self.assertEqual(0x046681E5, module.MixFwd([0xD4, 0xBF, 0x5D, 0x30]))
        self.assertEqual(0xD4BF5D30, module.MixInv([0x04, 0x66, 0x81, 0xE5]))

        # Source-compatible ShiftRows byte permutations and 64-bit rotates.
        src1 = list(range(8))
        src2 = list(range(8, 16))
        self.assertEqual([0, 5, 10, 15, 4, 9, 14, 3], module.ForwardShiftRows(src1, src2))
        self.assertEqual([0, 13, 10, 7, 4, 1, 14, 11], module.InverseShiftRows(src1, src2))
        value = 0x0123456789ABCDEF
        self.assertEqual(0xEF0123456789ABCD, module.crypto_rotate_integer(value, 8))
        self.assertEqual(0x8091A2B3C4D5E6F7, module.ROR64(value, 1))

    def test_probe_vectors(self) -> None:
        module = load_subject()
        dut = module.CryptoUtilsProbe()
        sim = Simulator(dut)

        def process() -> Any:
            yield dut.src1.eq(0x0123456789ABCDEF)
            yield dut.src2.eq(0x0F0E0D0C0B0A0908)
            yield dut.byte.eq(0x57)
            yield dut.coeff.eq(0x0B)
            yield Settle()
            self.assertEqual(0x0113579BD, (yield dut.shr32))
            self.assertEqual(0x0002468ACF13579B, (yield dut.shr64))
            self.assertEqual(0x00000000E26AF37B, (yield dut.ror32))
            self.assertEqual(0x8091A2B3C4D5E6F7, (yield dut.ror64))
            self.assertEqual(0x890E09670F0A45EF, (yield dut.forward_rows))
            self.assertEqual(0x0B0ECD67010A0DEF, (yield dut.inverse_rows))
            self.assertEqual(0xAE, (yield dut.xt2))
            self.assertEqual(0x77, (yield dut.xtn))
            self.assertEqual(0xAB, (yield dut.byte_enc))
            self.assertEqual(0x5B, (yield dut.aes))
            self.assertEqual(0xDA, (yield dut.iaes))
            self.assertEqual(0x8B, (yield dut.sm4))

        sim.add_process(process)
        sim.run()

    def test_deterministic_named_export(self) -> None:
        module = load_subject()
        first = module.build_verilog(None, {})
        second = module.build_verilog(None, {})
        self.assertEqual(first, second)
        self.assertRegex(first, r"\bmodule\s+CryptoUtilsProbe\b")
        self.assertGreater(len(first), 1000)
        self.assertNotEqual(hashlib.sha256(first.encode()).hexdigest(), "0" * 64)


if __name__ == "__main__":
    unittest.main()
