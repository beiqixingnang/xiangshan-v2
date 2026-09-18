"""Register completed bounded family subjects in the V2 core inventory."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "V2-Core-Rewrite-Inventory.json"

NEW = [
    {
        "id": "DebugTriggerFamily",
        "source_scala": ["scala/src/main/scala/xiangshan/backend/fu/NewCSR/Debug.scala"],
        "build_path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.DebugFamily-Hardware.py",
        "family_id": "core.backend.newcsr.debug",
        "closure_root": "core.backend.newcsr",
        "classification": "REWRITTEN",
        "disposition": "STRUCTURE_VERIFIED_DIRECT_BOUNDED",
        "v2_status": "VALIDATOR_PASS_BOUNDED",
        "reference_surface": ["upstream/src/main/scala/xiangshan/backend/fu/NewCSR/Debug.scala", "validation/v2-debug-family-results.json"],
    },
    {
        "id": "PrefetchFamily",
        "source_scala": ["scala/src/main/scala/xiangshan/mem/prefetch/SMSPrefetcher.scala", "scala/src/main/scala/xiangshan/mem/prefetch/L1PrefetchComponent.scala", "scala/src/main/scala/xiangshan/mem/prefetch/FDP.scala"],
        "build_path": "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Prefetch.Family-Hardware.py",
        "family_id": "core.memory.prefetch",
        "closure_root": "core.memory.prefetch",
        "classification": "REWRITTEN",
        "disposition": "STRUCTURE_VERIFIED_DIRECT_BOUNDED",
        "v2_status": "VALIDATOR_PASS_BOUNDED",
        "reference_surface": ["validation/v2-prefetch-family-results.json"],
    },
]

data = json.loads(PATH.read_text(encoding="utf-8"))
ids = {entry["id"] for entry in data["entries"]}
for entry in NEW:
    if entry["id"] not in ids:
        data["entries"].append(entry)
data["entries_status_counts"] = {}
for entry in data["entries"]:
    status = entry.get("v2_status", entry.get("disposition", "UNKNOWN"))
    data["entries_status_counts"][status] = data["entries_status_counts"].get(status, 0) + 1
data["status"] = "IMPLEMENTATION_WAVES_VALIDATED_BOUNDED_HIERARCHY_WAVE1"
data["acceptance_eligible"] = False
PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
print("registered", [entry["id"] for entry in NEW if entry["id"] in ids or entry in data["entries"]])
