"""Run one exact candidate test path, including governed dotted basenames."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = ROOT / "python/Program-System/System-Testing/Testing-Cpu"


def main() -> int:
    """Load the exact path and reject silent zero-test success."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--minimum-tests", type=int, default=1)
    args = parser.parse_args()
    path = (ROOT / args.test).resolve()
    if not path.is_relative_to(TEST_ROOT.resolve()) or not path.is_file():
        raise ValueError("test path must be an existing candidate CPU test")
    if args.minimum_tests < 1:
        raise ValueError("at least one actual test is required")
    name = "v2_direct_" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        if suite.countTestCases() < args.minimum_tests:
            raise ValueError(f"only {suite.countTestCases()} tests discovered; require {args.minimum_tests}")
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        return 0 if result.wasSuccessful() and result.testsRun >= args.minimum_tests else 1
    finally:
        sys.modules.pop(name, None)


if __name__ == "__main__":
    raise SystemExit(main())
