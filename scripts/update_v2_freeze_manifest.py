"""Update derived build telemetry after a bounded family batch."""

from __future__ import annotations

import json
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "V2-Rewrite-Freeze-Manifest.json"
data = json.loads(path.read_text(encoding="utf-8"))
sem = data["file_count_semantics"]
sem["current_distinct_build_paths"] = 109
sem["current_committed_build_paths"] = 95
sem["current_draft_build_paths"] = 14
sem["hierarchy_wave2_subject_paths"].extend([
    {"path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.DebugFamily-Hardware.py", "status": "DRAFT_VALIDATOR_PASS_BOUNDED"},
    {"path": "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Prefetch.Family-Hardware.py", "status": "DRAFT_VALIDATOR_PASS_BOUNDED"},
    {"path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.PMP.Family-Hardware.py", "status": "DRAFT_VALIDATOR_PASS_BOUNDED"},
    {"path": "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Store.Family-Hardware.py", "status": "DRAFT_VALIDATOR_PASS_BOUNDED"},
    {"path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Decode.ControlFamily-Hardware.py", "status": "DRAFT_VALIDATOR_PASS_BOUNDED"},
    {"path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Datapath.BypassPipeFamily-Hardware.py", "status": "DRAFT_VALIDATOR_PASS_BOUNDED"},
    {"path": "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Dcache.MissQueue.Family-Hardware.py", "status": "DRAFT_VALIDATOR_PASS_BOUNDED"},
    {"path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.NewCSR.ControlFamily-Hardware.py", "status": "DRAFT_VALIDATOR_PASS_BOUNDED"},
    {"path": "python/Program-System/System-Build/Build-Cpu/Cpu-Memory/Build-Cpu.Memory.Vector.Family-Hardware.py", "status": "DRAFT_VALIDATOR_PASS_BOUNDED"},
    {"path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Fu.FloatingPoint.Family-Hardware.py", "status": "DRAFT_VALIDATOR_PASS_BOUNDED"},
    {"path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Backend.Datapath.VectorFamily-Hardware.py", "status": "DRAFT_VALIDATOR_PASS_BOUNDED"},
    {"path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Frontend.Icache.Prefetch.Family-Hardware.py", "status": "DRAFT_VALIDATOR_PASS_BOUNDED"},
    {"path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Dependency.Difftest.StateFamily-Hardware.py", "status": "DRAFT_VALIDATOR_PASS_BOUNDED"},
    {"path": "python/Program-System/System-Build/Build-Cpu/Cpu-Core/Build-Cpu.Residual.LeafFamily-Hardware.py", "status": "DRAFT_VALIDATOR_PASS_BOUNDED_SOURCE_SPLIT_PENDING"},
])
unique_paths: list[dict[str, str]] = []
seen_paths: set[str] = set()
for item in sem["hierarchy_wave2_subject_paths"]:
    record = {"path": item, "status": "COMMITTED_BOUNDED"} if isinstance(item, str) else item
    if record["path"] not in seen_paths:
        unique_paths.append(record)
        seen_paths.add(record["path"])
sem["hierarchy_wave2_subject_paths"] = unique_paths
data["status"] = "FROZEN_COUNT_REWRITE_ACTIVE"
data["acceptance_eligible"] = False
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print("updated", path)
