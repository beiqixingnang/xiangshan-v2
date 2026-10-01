"""Prove the Decode leaf using a conservation-audited packed-literal view.

Only positional literals of statically sized packed arrays are normalized.
The locked reference and product Build remain untouched; this focused member
receipt cannot increment the full Decode family count.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import v2_strict_family_rail as rail
from v2_catalog_family_strict_validator import build_id_for, direct_path_for, resolve_build, source_record


EVIDENCE = rail.ROOT / "validation/v2-uopinfo-packed-reference-proof.json"
BASE_VIEW = rail.synthesizable_view
BASE_RUN = rail.run_wsl
PACKED = re.compile(
    r"^(?P<prefix>\s*wire\s+\[(?P<high>\d+):0\]\[(?P<bits>\d+):0\]\s+"
    r"(?P<name>\w+)\s*=\s*)'\{(?P<items>[^{};]+)\}(?P<suffix>;.*)$"
)
ELEMENT = re.compile(r"(?P<bits>\d+)'(?P<base>[bdh])(?P<value>[0-9a-fA-F_]+)")


def normalize_packed(text: str) -> tuple[str, dict[str, object]]:
    """Remove only a packed positional pattern's apostrophe, preserving bits."""
    original = text.splitlines()
    projected: list[str] = []
    changes = []
    for line in original:
        match = PACKED.fullmatch(line)
        if match is None:
            projected.append(line)
            continue
        width = int(match["bits"]) + 1
        items = [item.strip() for item in match["items"].split(",")]
        if len(items) != int(match["high"]) + 1:
            raise AssertionError("packed array cardinality differs from initializer")
        for item in items:
            element = ELEMENT.fullmatch(item)
            if element is None or int(element["bits"]) != width:
                raise AssertionError("only explicit equal-width binary/decimal/hex constants are supported")
            number = int(element["value"].replace("_", ""), {"b": 2, "d": 10, "h": 16}[element["base"]])
            if number >= 1 << width:
                raise AssertionError("initializer constant exceeds its declared width")
        replacement = match["prefix"] + "{" + match["items"] + "}" + match["suffix"]
        projected.append(replacement)
        changes.append({"name": match["name"], "elements": len(items), "element_bits": width,
                        "before": line, "after": replacement})
    before = Counter(original)
    after = Counter(projected)
    if after - before != Counter(change["after"] for change in changes) \
            or before - after != Counter(change["before"] for change in changes):
        raise AssertionError("packed-pattern conservation failed")
    return "\n".join(projected) + "\n", {
        "changes": changes, "same_line_count": len(original) == len(projected),
        "multiplicity_conserved": True,
        "sha256_before": hashlib.sha256(text.encode()).hexdigest(),
        "sha256_after": hashlib.sha256(("\n".join(projected) + "\n").encode()).hexdigest(),
    }


def packed_view(text: str, top: str, rename: bool) -> tuple[str, dict[str, object]]:
    """Combine the packed-literal projection with the existing strict view."""
    projected, packed_audit = normalize_packed(text)
    view, audit = BASE_VIEW(projected, top, rename)
    audit["packed_positional_projection"] = packed_audit
    audit["view_trusted"] = audit["view_trusted"] is True \
        and packed_audit["multiplicity_conserved"] is True \
        and packed_audit["same_line_count"] is True
    return view, audit


def mapped_rom_run(command: list[str], timeout: int = rail.GATE_TIMEOUT_SECONDS) -> dict:
    """Lower LUT ROMs before SAT on both baseline and mutant executions."""
    transformed = list(command)
    if transformed[0] == "yosys" and "-p" in transformed:
        index = transformed.index("-p") + 1
        script = transformed[index]
        pattern = "flatten; opt; sat -prove mismatch 0"
        if pattern in script:
            transformed[index] = script.replace(pattern, "flatten; memory; opt; sat -prove mismatch 0")
    return BASE_RUN(transformed, timeout)


def main() -> int:
    build = resolve_build("Backend.Decode.ControlFamily")
    direct = direct_path_for(build)
    command = [sys.executable, "-B", str(direct)]
    test = subprocess.run(command, cwd=rail.ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)
    if test.returncode:
        raise AssertionError("direct test failed: " + (test.stdout + test.stderr)[-1200:])
    module = rail.load_module("uopinfo_packed_target", build)
    # The shared producer on disk and its historical receipts remain unchanged.
    rail.synthesizable_view = packed_view
    rail.run_wsl = mapped_rom_run
    runner = rail.FamilyRail(build, build_id_for(build), EVIDENCE)
    runner.work.mkdir(parents=True, exist_ok=True)
    item = runner.prepare(module, "UopInfoGen")
    failures = runner.cheap_static_failures(item)
    if not failures:
        lint, original = runner.lint_gate(item)
        if lint["status"] != "PASS" or original["status"] != "PASS":
            failures.append("DUT or original reference lint failed")
    item["static_blocked"] = bool(failures)
    result = runner.prove(item)
    passed = not failures and runner.formal_result_pass(result, item)
    controls = runner.negative_control([item]) if passed else {"status": "NOT_RUN"}
    complete = passed and runner.controls_result_pass(controls, [item])
    payload = {
        "schema_version": 1, "kind": "V2_PACKED_LITERAL_MEMBER_PROOF",
        "build_id": build_id_for(build), "members": ["UopInfoGen"],
        "status": "PASS_MEMBER_PROOFS_NON_COUNTING" if complete else "STRICT_PENDING",
        "strict_complete_count_delta": 0, "strict_complete_eligible": False,
        "acceptance_eligible": False,
        "sources": {"build": source_record(build), "direct": source_record(direct),
                    "validator": source_record(Path(__file__).resolve()),
                    "base_view": source_record(Path(rail.__file__).resolve()),
                    "locked_references": [source_record(path) for path in item["locked_sources"]]},
        "static_failures": failures, "prepared": runner.path_value(item),
        "proof_lowering": "unchanged equations; positional packed constant projection; memory mapping before baseline/mutant SAT",
        "formal": result, "negative_control": controls,
        "direct": {"command": command, "returncode": test.returncode,
                   "output_tail": (test.stdout + test.stderr)[-1200:]},
        "unclosed": ["Other Decode members, parent closure and CPU acceptance remain pending."],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "static_failures": failures,
                      "baseline": "PASS" if passed else "FAIL", "negative": controls["status"]}))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
