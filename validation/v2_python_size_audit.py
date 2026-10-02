"""Measure candidate Build size against an explicit Git baseline."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PREFIX = "python/Program-System/System-Build/Build-Cpu/"


def metrics(source: str) -> dict[str, int]:
    lines = source.splitlines()
    docstrings: set[int] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            docstrings.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return {"raw": len(lines), "nonempty": sum(bool(line.strip()) for line in lines),
            "code": sum(bool(line.strip()) and not line.lstrip().startswith("#") and index not in docstrings
                        for index, line in enumerate(lines, 1))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    args = parser.parse_args()
    baseline = subprocess.run(["git", "rev-parse", "--verify", args.baseline + "^{commit}"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    paths = subprocess.run(["git", "ls-tree", "-r", "--name-only", baseline, PREFIX], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", check=True).stdout.splitlines()
    paths = [path for path in paths if path.endswith(".py")]
    current = {path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
               for path in (ROOT / PREFIX).rglob("*.py")}
    before = {}
    for path in paths:
        source = subprocess.run(["git", "show", baseline + ":" + path], cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8", check=True).stdout
        before[path] = source
    old = {path: metrics(source) for path, source in before.items()}
    new = {path: metrics(source) for path, source in current.items()}
    totals_before = {key: sum(row[key] for row in old.values()) for key in ("raw", "nonempty", "code")}
    totals_after = {key: sum(row[key] for row in new.values()) for key in ("raw", "nonempty", "code")}
    print(json.dumps({"baseline": baseline, "scope": "candidate Build Python only; size never establishes implementation",
                      "before_files": len(old), "current_files": len(new), "before": totals_before,
                      "current": totals_after, "delta": {key: totals_after[key] - totals_before[key] for key in totals_before},
                      "changed": {path: {key: new.get(path, {}).get(key, 0) - old.get(path, {}).get(key, 0)
                                         for key in totals_before}
                                  for path in sorted(set(old) | set(new)) if before.get(path) != current.get(path)}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
