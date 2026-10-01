"""Reject declared contract-only families before tool or formal preparation.

The existing ABI/tool preflight remains a prerequisite check. An explicit
CONTRACT_ONLY declaration blocks this entire Build; unknown implementation
coverage still requires behavioral tests and a locked-reference proof.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import v2_strict_family_rail as rail
from v2_catalog_family_strict_validator import build_id_for, resolve_build, source_record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True)
    args = parser.parse_args()
    build = resolve_build(args.build)
    module = rail.load_module("behavior_preflight", build)
    members = rail.enumerate_members(module, build)
    declared = getattr(module, "CONTRACT_ONLY_MEMBERS", None)
    if declared is not None and (not isinstance(declared, (tuple, list))
                                 or any(not isinstance(name, str) for name in declared)
                                 or not set(declared).issubset(members)):
        raise ValueError("contract-only declaration must be a subset of the Build catalog")
    blocked = [name for name in members if declared is not None and name in declared]
    payload = {
        "schema_version": 1, "kind": "V2_DECLARED_BEHAVIOR_PREFLIGHT",
        "build_id": build_id_for(build), "strict_complete_count_delta": 0,
        "acceptance_eligible": False, "formal": "NOT_RUN", "tool_preparation": "NOT_RUN",
        "status": "BLOCKED_CONTRACT_ONLY" if blocked else "BEHAVIOR_DECLARATION_CHECK_COMPLETE",
        "members": members, "contract_only_members": blocked,
        "declaration_present": declared is not None,
        "ready_for_formal": False,
        "remaining_gates": (["Implement the declared contract-only members and behavioral direct tests."]
                            if blocked else ["This check does not prove implementation; direct behavior, ABI/tool and strict gates remain required."]),
        "sources": {
            "python_build": source_record(build),
            "validator": source_record(Path(__file__).resolve()),
            "validator_dependencies": {
                "catalog_resolver": source_record(rail.ROOT / "validation/v2_catalog_family_strict_validator.py"),
                "strict_family_rail": source_record(rail.ROOT / "validation/v2_strict_family_rail.py"),
            },
        },
    }
    slug = payload["build_id"].lower().replace(".", "-")
    evidence = rail.ROOT / "validation" / f"v2-{slug}-behavior-preflight-results.json"
    evidence.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    print(json.dumps({key: payload[key] for key in (
        "status", "build_id", "contract_only_members", "ready_for_formal", "formal")}), flush=True)
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
