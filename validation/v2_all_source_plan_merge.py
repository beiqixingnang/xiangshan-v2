"""Freeze complete source ownership from three reviewed disjoint scan partitions."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "validation/v2-all-source-scan-seed.json"
FRAGMENTS = (
    "validation/v2-all-source-core-scan.json",
    "validation/v2-all-source-infrastructure-scan.json",
    "validation/v2-all-source-dependency-scan.json",
)
OUTPUT = ROOT / "validation/v2-all-source-rewrite-plan.json"
MARKDOWN = ROOT / "V2-All-Source-Rewrite-Plan.md"
CLASSIFICATIONS = {
    "HARDWARE_BEHAVIOR", "ELABORATION_CONFIG", "HOST_TOOL", "TEST_ONLY",
    "DECLARATION_SUPPORT", "MIXED_HARDWARE_SUPPORT",
}
HARDWARE_CLASSIFICATIONS = {"HARDWARE_BEHAVIOR", "MIXED_HARDWARE_SUPPORT"}
BUILD_PREFIX = "python/Program-System/System-Build/Build-Cpu/"
RUNTIME_PREFIX = "python/Program-System/System-Runtime/Runtime-Hdl/"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def valid_build_path(path: str) -> bool:
    candidate = Path(path)
    return (path.startswith((BUILD_PREFIX, RUNTIME_PREFIX)) and ".." not in candidate.parts
            and candidate.name.startswith(candidate.parent.name + "-")
            and candidate.name.endswith("-Hardware.py"))


def unique_metadata(items: list[Any]) -> list[Any]:
    encoded = {json.dumps(item, ensure_ascii=False, sort_keys=True): item for item in items}
    return [encoded[key] for key in sorted(encoded)]


def freeze() -> dict[str, Any]:
    seed = read_json(SEED)
    expected = {row["path"]: row for row in seed["files"]}
    rows: dict[str, dict[str, Any]] = {}
    targets: dict[str, dict[str, Any]] = {}
    fragment_records = []
    for filename in FRAGMENTS:
        path = ROOT / filename
        fragment = read_json(path)
        fragment_records.append({"path": filename, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        for target in fragment["python_files"] + fragment.get("python_runtime_files", []):
            target_path = target["path"]
            if not valid_build_path(target_path):
                raise ValueError("invalid proposed Build naming/path: " + target_path)
            if target_path not in targets:
                targets[target_path] = dict(target)
                targets[target_path]["contributing_scan_fragments"] = [filename]
            else:
                targets[target_path]["contributing_scan_fragments"].append(filename)
                for key in ("sources", "hardware_symbols", "required_configuration_modes", "needed_companion_dependencies"):
                    targets[target_path][key] = unique_metadata(targets[target_path].get(key, []) + target.get(key, []))
        for row in fragment["files"]:
            path_key = row["path"]
            if path_key in rows or path_key not in expected:
                raise ValueError("duplicate or out-of-scope source: " + path_key)
            if row["classification"] not in CLASSIFICATIONS or not row.get("reason"):
                raise ValueError("missing reviewed source disposition: " + path_key)
            if row["classification"] in HARDWARE_CLASSIFICATIONS and not row.get("python_targets"):
                raise ValueError("hardware-bearing file has no planned Python owner: " + path_key)
            if row.get("python_targets") and not row.get("feature_obligations"):
                raise ValueError("planned implementation has no explicit source feature obligations: " + path_key)
            for target_path in row.get("python_targets", []):
                if not valid_build_path(target_path):
                    raise ValueError("invalid source target path: " + target_path)
            declared = Counter((item["kind"], item["name"]) for item in expected[path_key]["declarations"])
            ownership = Counter((item["kind"], item["name"]) for item in row["declaration_owners"])
            if declared != ownership:
                raise ValueError("declaration ownership does not exactly cover source: " + path_key)
            for declaration in row["declaration_owners"]:
                if not declaration.get("disposition"):
                    raise ValueError("declaration has no disposition: " + path_key)
                owner = declaration.get("python_target")
                if owner and owner not in row.get("python_targets", []):
                    raise ValueError("declaration owner outside file target list: " + path_key)
            raw = (ROOT / path_key).read_bytes()
            checksum = hashlib.sha256(raw).hexdigest()
            if checksum != expected[path_key]["sha256"]:
                raise ValueError("source changed during scan: " + path_key)
            row = dict(row)
            row.update({"sha256": checksum, "scala_lines": expected[path_key]["lines"],
                        "locked_module_definitions": expected[path_key]["locked_modules"],
                        "implementation_status": "PLANNED_REWRITE_OR_AUDIT_REQUIRED",
                        "behavior_validation_status": "DEFERRED_UNTIL_COMPLETE_SOURCE_COVERAGE"})
            rows[path_key] = row
    if set(rows) != set(expected):
        raise ValueError("unclassified sources: " + repr(sorted(set(expected) - set(rows))))
    owners: dict[str, set[str]] = defaultdict(set)
    for path_key, row in rows.items():
        for owner in row.get("python_targets", []):
            if owner not in targets:
                raise ValueError("file owner absent from Python file plan: " + owner)
            owners[owner].add(path_key)
    for owner, target in targets.items():
        target["sources"] = sorted(owners[owner])
        target["owned_scala_file_count"] = len(owners[owner])
        target["existing"] = (ROOT / owner).is_file()
        target["state"] = "REWRITE_OR_SOURCE_COMPLETENESS_AUDIT_REQUIRED"
        target["kind"] = "runtime" if owner.startswith(RUNTIME_PREFIX) else "build"
        category = "Testing-Hdl" if target["kind"] == "runtime" else "Testing-Cpu"
        function = Path(owner).name.removeprefix(Path(owner).parent.name + "-").removesuffix("-Hardware.py")
        target["test_path"] = f"python/Program-System/System-Testing/{category}/{category}-{function}-Hardware.py"
    hierarchy = read_json(ROOT / "validation/v2-locked-hierarchy.json")
    source_modules: dict[str, set[str]] = defaultdict(set)
    for source, row in rows.items():
        for module in row["locked_module_definitions"]:
            source_modules[module].add(source)
    locked_rows = []
    for name, module in sorted(hierarchy["modules"].items()):
        hardware_sources = sorted(source for source in source_modules[name]
                                  if rows[source]["classification"] in HARDWARE_CLASSIFICATIONS)
        candidates = sorted({owner for source in hardware_sources for owner in rows[source]["python_targets"]
                             if targets[owner]["kind"] == "build"})
        locked_rows.append({"module": name, "source_files": sorted(source_modules[name]),
                            "planned_build_candidates": candidates, "children": module["children"],
                            "state": "SOURCE_FAMILY_OWNER_PLANNED_EXACT_MODULE_IMPLEMENTATION_PENDING" if candidates else "MISSING_HARDWARE_SOURCE_OWNER",
                            "implementation_claimed": False})
    missing_locked = [row["module"] for row in locked_rows if not row["planned_build_candidates"]]
    blackbox_rows = []
    for row in locked_rows:
        if row["source_files"]:
            continue
        name = row["module"]
        if name.startswith("DiffExt"):
            feature = "Dependency.Difftest.StateFamily"
            scope = "simulation_endpoint_and_external_host_contract"
        elif name.startswith("CSA") or name in {"ClockGate", "PrintCommitIDModule", "r4_qds_v2", "r4_qds_v2_spec"}:
            feature = "Dependency.Utility.ResidualFamily"
            scope = "blackbox_or_inlined_resource_hardware_and_environment_contract"
        else:
            continue
        owner = BUILD_PREFIX + "Cpu-Core/Cpu-Core-" + feature + "-Hardware.py"
        if owner not in targets:
            raise ValueError("blackbox obligation family absent from source plan: " + owner)
        reference = ROOT / "validation/reference-sv" / (name + ".sv")
        if not reference.is_file():
            raise ValueError("locked blackbox reference missing: " + name)
        obligation = {"module": name, "python_target": owner, "scope": scope,
                      "locked_reference": reference.relative_to(ROOT).as_posix(),
                      "locked_reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
                      "missing_scala_location": True, "implementation_status": "REWRITE_OR_CLOSED_CONTRACT_REQUIRED",
                      "acceptance_eligible": False}
        blackbox_rows.append(obligation)
        row["planned_build_candidates"] = [owner]
        row["state"] = "EXPLICIT_BLACKBOX_OWNER_PLANNED_BEHAVIOR_AND_ENVIRONMENT_PENDING"
    missing_locked = [row["module"] for row in locked_rows if not row["planned_build_candidates"]]
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    physical_builds = {path.relative_to(ROOT).as_posix() for path in (ROOT / BUILD_PREFIX).rglob("*.py")}
    planned_builds = {path for path in targets if targets[path]["kind"] == "build"}
    planned_runtime = {path for path in targets if targets[path]["kind"] == "runtime"}
    new_paths = planned_builds - physical_builds
    all_tests = {}
    for path in physical_builds | planned_builds | planned_runtime:
        directory = "Testing-Hdl" if path in planned_runtime else "Testing-Cpu"
        function = Path(path).name.removeprefix(Path(path).parent.name + "-").removesuffix("-Hardware.py")
        all_tests[path] = f"python/Program-System/System-Testing/{directory}/{directory}-{function}-Hardware.py"
    retained = [{"path": path, "role": "EXISTING_SUBJECT_REQUIRES_SOURCE_OR_CONSTITUENT_RECONCILIATION",
                 "disposition": "RETAIN_UNTIL_EXACT_REUSE_OR_RETIREMENT_REVIEW", "source_coverage_credit": False,
                 "direct_test": all_tests[path]}
                for path in sorted(physical_builds - set(targets))]
    classes = dict(Counter(row["classification"] for row in rows.values()))
    return {
        "kind": "V2_ALL_SOURCE_AGGREGATE_REWRITE_FROZEN_PLAN", "source_commit": seed["source_commit"],
        "phase": "SOURCE_FIRST_BULK_REWRITE_EXPORT_ONLY", "auxiliary_commit": git, "inputs": fragment_records,
        "summary": {"all_scala_files": len(rows), "scala_lines": sum(row["scala_lines"] for row in rows.values()),
                    "declarations_assigned": sum(len(row["declaration_owners"]) for row in rows.values()),
                    "classifications": classes, "existing_build_files": len(physical_builds),
                    "source_owned_python_files": len(targets), "reuse_existing_build_files": len(set(targets) & physical_builds),
                    "planned_runtime_files": len(planned_runtime),
                    "new_runtime_files_needed": sum(not (ROOT / path).is_file() for path in planned_runtime),
                    "new_build_files_needed": len(new_paths), "new_direct_test_files_needed": sum(not (ROOT / targets[path]["test_path"]).is_file() for path in targets),
                    "all_required_direct_test_files_needed": sum(not (ROOT / path).is_file() for path in all_tests.values()),
                    "all_planned_python_implementation_files": len(physical_builds | planned_builds) + len(planned_runtime),
                    "planned_total_build_files": len(physical_builds | planned_builds),
                    "existing_builds_without_source_plan": len(physical_builds - set(targets))},
        "new_build_paths": sorted(new_paths), "existing_builds_without_source_plan": sorted(physical_builds - set(targets)),
        "locked_module_source_mapping": locked_rows, "locked_module_source_mapping_gaps": missing_locked,
        "non_scala_artifact_obligations": blackbox_rows,
        "retained_existing_build_review": retained,
        "files": [rows[path] for path in sorted(rows)], "python_files": [targets[path] for path in sorted(targets)],
        "mapping_partition_complete": True, "locked_module_source_mapping_complete": not missing_locked,
        "rewrite_complete": False, "all_exports_pass": False,
        "behavior_verified": False, "acceptance_eligible": False,
        "coverage_policy": "All files and declarations have explicit planned dispositions. Mapped sources and generated Verilog do not prove executable coverage or behavior equivalence.",
        "next_gate": "Bulk implement actual equations/configuration in owned families; audit every source feature and native export before behavioral validation.",
    }


def render(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = ["# V2 全源码聚合重写计划", "", "本计划按全部已下载 Scala 源码冻结去向。硬件功能先批量重写并通过基本导出门禁，完整覆盖审查后统一行为验证。映射和导出均不授予 ACCEPTED。", "",
             "| 项目 | 数量 |", "| --- | ---: |"]
    labels = {"all_scala_files": "Scala 文件", "scala_lines": "Scala 总行数", "declarations_assigned": "已分配源码声明",
              "existing_build_files": "现有 Build", "reuse_existing_build_files": "需审查或扩充的现有 Build",
              "new_build_files_needed": "新增聚合 Build", "planned_total_build_files": "规划完成后 Build 总数",
              "new_runtime_files_needed": "新增纯 Python Runtime", "all_planned_python_implementation_files": "候选实现 Python 总数",
              "all_required_direct_test_files_needed": "待补同功能直接测试"}
    lines.extend(f"| {label} | {summary[key]} |" for key, label in labels.items())
    lines += ["", "其中 93 个现有 Build 被直接分配源码职责，其余 30 个现有主体保留待核对其子构件复用、来源迁移或退出职责，不能静默删除，也不能取得源码覆盖信用。清单映射共有 109 个 Build 所有者及 1 个 Runtime；候选总数仍包括这 30 个保留主体。", "",
              "非硬件文件逐项记录为测试、宿主工具、声明支持或生成配置；当前实例未使用的硬件仍纳入实现范围。每个声明和功能义务在 JSON 中有明确所有者，不以文件数量或空壳代替实现。", "",
              "锁定层级的 1976 个定义都有规划候选；其中 30 个缺 Scala 来源注解的黑盒/仿真端点单独保留 reference 哈希、行为与环境合同义务。规划归属不等于已实现或已验收。", "",
              "产品要求：纯标准库 + Amaranth、固定五区、准确公开 API、本地化、函数名以字母开头、无来源清单或嵌入 HDL；Build 只原生导出其实现，依赖由公开参数注入。直接测试按同功能名及四区模板登记。", "",
              "重写阶段只运行结构/精确导入/语法/批次静态检查/原生同名 Verilog 导出，保存 EXPORT_PASS_BEHAVIOR_UNVERIFIED。完整源码义务和必要配置都完成后，才运行 direct 行为、锁定参考差分、formal、父级/顶层、许可证与验收。", "",
              "| Python 聚合文件 | 现有/新增 | 对应 Scala 数 | 职责 |", "| --- | --- | ---: | --- |"]
    lines.extend(f"| `{row['path']}` | {'现有' if row['existing'] else '新增'} | {row['owned_scala_file_count']} | {row.get('responsibility', '').replace('|', '/')} |" for row in payload["python_files"])
    lines += ["", "完整逐文件、逐声明、参数模式与源码哈希映射见 `validation/v2-all-source-rewrite-plan.json`。后续新增或拆分需更新本计划及覆盖账本；不得以冻结文件数量排除真实功能。", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    payload = freeze()
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    MARKDOWN.write_text(render(payload), encoding="utf-8", newline="\n")
    print(json.dumps(payload["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
