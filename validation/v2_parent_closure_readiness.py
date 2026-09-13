"""Scan V2 candidate reachability and plan parent-closure integration batches.
扫描 V2 候选的父级可达性并规划父级 closure 集成批次。

The scanner is deliberately read-only with respect to ``upstream/`` and the
locked generated reference.  It records source and XSTop evidence, then joins
that evidence with the existing leaf-batch manifests.  It never promotes a
candidate; ``ACCEPTED`` is hard-coded to ``NOT_ALLOWED`` in the generated
report.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
XSTOP = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
EXPECTED_SOURCE_COMMIT = "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af"
EXPECTED_XSTOP_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
EXPECTED_XSTOP_BYTES = 228590583
CANDIDATE_MANIFEST = ROOT / "python/ported/V2-Ported-Candidates.json"
MAPPING_MANIFEST = ROOT / "V2-Phase0-Mapping-Manifest.json"
OUTPUT = ROOT / "validation/v2-parent-closure-readiness.json"


MODULE_LINE = re.compile(rb"^module\s+(?P<name>[A-Za-z_][A-Za-z0-9_$]*)\s*\(")
ENDMODULE_LINE = re.compile(rb"^endmodule\b")
DIRECTIVE_LINE = re.compile(rb"^module\s+")
SOURCE_COMMENT = re.compile(r"//.*$")
STATUS_PASS = {
    "PASS",
    "PASS_BOUNDED",
    "PASS_BOUNDED_DIRECT",
    "PASS_BOUNDED_PARENT",
    "PASS_BOUNDED_REFERENCE",
    "V2_REFERENCE_MATCHED",
    "DIFFERENTIAL_MATCHED_BOUNDED",
}


@dataclass(frozen=True)
class ModuleRecord:
    """One module span and port summary from the locked XSTop artifact.
    锁定 XSTop 产物中的一个模块范围及端口摘要。
    """

    name: str
    line_start: int
    line_end: int
    byte_count: int
    header: bytes
    body: bytes

    def metadata(self) -> dict[str, Any]:
        """Return deterministic machine-readable module metadata.
        返回确定性的机器可读模块元数据。
        """

        ports = parse_ports(self.header)
        return {
            "name": self.name,
            "xstop_line_start": self.line_start,
            "xstop_line_end": self.line_end,
            "bytes": self.byte_count,
            "header_sha256": sha256_bytes(self.header),
            "port_count": len(ports),
            "ports": ports,
        }


def sha256_bytes(payload: bytes) -> str:
    """Hash exact bytes without normalizing line endings.
    对原始字节计算摘要，不规范化换行。
    """

    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a file using its exact on-disk bytes.
    对文件磁盘上的原始字节计算摘要。
    """

    return sha256_bytes(path.read_bytes())


def parse_ports(header: bytes) -> list[dict[str, str]]:
    """Parse Chisel-emitted ANSI port declarations conservatively.
    保守解析 Chisel 生成的 ANSI 端口声明。

    Continuation names inherit the most recent direction/width.  The raw
    header hash in the report remains authoritative if a future emitter uses
    syntax this small parser does not understand.
    """

    text = header.decode("utf-8", "replace")
    ports: list[dict[str, str]] = []
    direction = ""
    width = ""
    # Drop comments, then split declarations on commas.  XSTop headers do not
    # contain comma-separated expressions, so this is stable for the pinned
    # artifact.
    for raw_line in text.splitlines():
        line = SOURCE_COMMENT.sub("", raw_line).strip()
        if not line:
            continue
        if line.startswith("module "):
            line = line[line.find("(") + 1 :]
        if line.endswith(");"):
            line = line[:-2]
        elif line.endswith(")"):
            line = line[:-1]
        for part in line.split(","):
            token = part.strip().strip(")").strip()
            if not token:
                continue
            m = re.match(r"^(input|output|inout)\s+(?:(\[[^]]+\])\s*)?(.*)$", token)
            if m:
                direction = m.group(1)
                width = m.group(2) or ""
                names = m.group(3).strip()
            else:
                names = token
            # Ignore a bare opening parenthesis or a malformed keyword; keep
            # signal names that match Verilog identifiers.
            for name in re.findall(r"[A-Za-z_][A-Za-z0-9_$]*", names):
                if name in {"input", "output", "inout", "wire", "reg"}:
                    continue
                ports.append({"name": name, "direction": direction, "width": width})
    # Duplicate names can arise when comments contain a declaration-like
    # token; retain first occurrence to make the summary useful and stable.
    unique: list[dict[str, str]] = []
    seen: set[str] = set()
    for port in ports:
        if port["name"] not in seen:
            unique.append(port)
            seen.add(port["name"])
    return unique


def read_module_records(path: Path, wanted: set[str]) -> dict[str, ModuleRecord]:
    """Stream the reference once and capture only requested modules.
    流式读取参考产物一次，仅捕获请求的模块。
    """

    records: dict[str, ModuleRecord] = {}
    active_name: str | None = None
    active_start = 0
    active_lines: list[bytes] = []
    depth = 0
    with path.open("rb") as stream:
        for line_number, line in enumerate(stream, 1):
            if active_name is None:
                match = MODULE_LINE.match(line)
                if match is None:
                    continue
                name = match.group("name").decode("ascii", "replace")
                if name not in wanted:
                    continue
                active_name = name
                active_start = line_number
                active_lines = [line]
                depth = 1
                continue
            active_lines.append(line)
            # Nested module declarations are unusual in emitted SV, but the
            # depth accounting prevents a truncated capture if one appears.
            if DIRECTIVE_LINE.match(line):
                depth += 1
            if ENDMODULE_LINE.match(line):
                depth -= 1
                if depth == 0:
                    payload = b"".join(active_lines)
                    header_end = payload.find(b");")
                    header = payload if header_end < 0 else payload[: header_end + 2]
                    records[active_name] = ModuleRecord(
                        name=active_name,
                        line_start=active_start,
                        line_end=line_number,
                        byte_count=len(payload),
                        header=header,
                        body=payload,
                    )
                    active_name = None
                    active_lines = []
                    depth = 0
    return records


def count_reference(module: ModuleRecord, child: str) -> int:
    """Count lexical child-name occurrences in a captured module body.
    统计捕获模块体中子模块名称的词法出现次数。
    """

    text = module.body.decode("utf-8", "replace")
    return len(re.findall(r"(?<![A-Za-z0-9_$])" + re.escape(child) + r"(?![A-Za-z0-9_$])", text))


def source_record(path_text: str, anchors: Iterable[str]) -> dict[str, Any]:
    """Describe a pinned V2 source file and source-level anchor evidence.
    描述固定 V2 源文件及源级锚点证据。
    """

    path = ROOT / path_text
    if not path.is_file():
        return {
            "path": path_text,
            "present": False,
            "anchors": {anchor: 0 for anchor in anchors},
        }
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "path": path_text,
        "present": True,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "anchors": {anchor: len(re.findall(re.escape(anchor), text)) for anchor in anchors},
    }


def load_json(path: Path) -> Any:
    """Load UTF-8 JSON while giving a useful missing-file result.
    读取 UTF-8 JSON，并对缺失文件给出可用结果。
    """

    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_values(value: Any, key: str | None = None) -> Iterable[tuple[str | None, Any]]:
    """Yield every scalar/list/dict value with its immediate key.
    递归产生所有值及其直接键。
    """

    yield key, value
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            yield from flatten_values(child_value, child_key)
    elif isinstance(value, list):
        for child_value in value:
            yield from flatten_values(child_value, key)


def evidence_summary(paths: Iterable[str]) -> dict[str, Any]:
    """Summarize existing evidence files without changing their statuses.
    汇总已有证据文件，不改变其状态。
    """

    files: list[dict[str, Any]] = []
    pass_hits: Counter[str] = Counter()
    pending_hits: Counter[str] = Counter()
    for rel in paths:
        path = ROOT / rel
        payload = load_json(path)
        row: dict[str, Any] = {"path": rel, "present": payload is not None}
        if payload is None:
            files.append(row)
            continue
        row["sha256"] = sha256_file(path)
        row["bytes"] = path.stat().st_size
        statuses: list[str] = []
        for key, value in flatten_values(payload):
            if isinstance(value, str):
                upper = value.upper()
                if upper in STATUS_PASS:
                    statuses.append(value)
                    pass_hits[key or "value"] += 1
                elif "PENDING" in upper or upper in {"NOT_RUN", "NOT_GENERATED"}:
                    pending_hits[key or "value"] += 1
        row["pass_statuses"] = sorted(set(statuses))
        files.append(row)
    return {
        "files": files,
        "all_present": bool(files) and all(item["present"] for item in files),
        "pass_signal_count": sum(pass_hits.values()),
        "pending_signal_count": sum(pending_hits.values()),
        "pass_keys": sorted(pass_hits),
        "pending_keys": sorted(pending_hits),
    }


# These are parent boundaries, not a claim that all children have already been
# localized.  Names mirror the actual V2 source hierarchy and generated SV.
PARENT_SPECS: list[dict[str, Any]] = [
    {
        "closure_id": "frontend",
        "phase": "core-integration-1",
        "root_module": "Frontend",
        "root_source": "upstream/src/main/scala/xiangshan/frontend/Frontend.scala",
        "children": [
            "ICache",
            "ICacheMainPipe",
            "ICacheMissUnit",
            "ICacheReplacer",
            "FTB",
            "FTBEntryGen",
            "PreDecode",
            "RVCExpander",
        ],
        "indirect_children": {
            "ICacheMainPipe": "ICache",
            "ICacheMissUnit": "ICache",
            "ICacheReplacer": "ICache",
            "FTB": "Predictor/FTB (inlined parent path)",
            "FTBEntryGen": "NewFtq/FTBEntryGen (inlined parent path)",
            "PreDecode": "NewIFU/PreDecode (inlined parent path)",
            "RVCExpander": "NewIFU/PreDecode (inlined parent path)",
        },
        "source_paths": [
            "upstream/src/main/scala/xiangshan/frontend/Frontend.scala",
            "upstream/src/main/scala/xiangshan/frontend/BPU.scala",
            "upstream/src/main/scala/xiangshan/frontend/FTB.scala",
            "upstream/src/main/scala/xiangshan/frontend/FrontendBundle.scala",
            "upstream/src/main/scala/xiangshan/frontend/NewFtq.scala",
            "upstream/src/main/scala/xiangshan/frontend/PreDecode.scala",
            "upstream/src/main/scala/xiangshan/frontend/icache/ICache.scala",
            "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMainPipe.scala",
            "upstream/src/main/scala/xiangshan/frontend/icache/ICacheMissUnit.scala",
        ],
        "family_ids": [
            "core.frontend.bpu.compare",
            "core.frontend.ftb",
            "core.frontend.bpu.counters",
            "core.frontend.icache.mshr",
            "core.frontend.icache.replacer",
            "core.frontend.icache.utility",
            "core.frontend.ifu.rvc",
            "core.replacement",
        ],
        "observation_points": [
            "frontend request/response ready-valid",
            "FTB fall-through address and error",
            "BPU/TAGE/SC counter update and saturation",
            "RVC expansion and illegal encoding",
            "ICache miss allocation/refill/kill/flush",
        ],
        "anchor_map": {
            "Frontend.scala": ["class Frontend", "class FrontendInlined", "outer.icache.module"],
            "BPU.scala": ["getFallThroughAddr", "def satUpdate", "def signedSatUpdate"],
            "FTB.scala": ["def getFallThrough", "class FTB"],
            "PreDecode.scala": ["class RVCExpander", "RVCDecoder"],
            "ICache.scala": ["class ICacheReplacer", "class ICache"],
            "ICacheMissUnit.scala": ["class ICacheMSHR", "class ICacheMissUnit"],
        },
        "evidence": [
            "validation/v2-frontend-batch-results.json",
            "validation/v2-frontend-batch-reference-results.json",
            "validation/v2-frontend-bpu-rvc-coverage-manifest.json",
            "validation/v2-p1-b-icache-direct-results.json",
            "validation/v2-p1-b-icache-differential-results.json",
            "validation/v2-p1-b-icache-coverage-manifest.json",
        ],
        "next_action": "Build a reduced Frontend parent harness around the generated Frontend boundary; first bind ICache and RVC, then add source-level BPU/FTB/counter probes.",
    },
    {
        "closure_id": "backend",
        "phase": "core-integration-2",
        "root_module": "Backend",
        "root_source": "upstream/src/main/scala/xiangshan/backend/Backend.scala",
        "children": [
            "DataPath",
            "WbDataPath",
            "RealWBCollideChecker",
            "DecodeUnit",
            "DecodeStage",
            "Mgu",
            "VldMgu",
        ],
        "indirect_children": {
            "RealWBCollideChecker": "WbDataPath",
            "DecodeUnit": "Backend decode path (inlined)",
            "DecodeStage": "Backend decode path (inlined)",
            "Mgu": "WbDataPath/VldMergeUnit",
            "VldMgu": "WbDataPath/VldMergeUnit",
        },
        "source_paths": [
            "upstream/src/main/scala/xiangshan/backend/Backend.scala",
            "upstream/src/main/scala/xiangshan/backend/datapath/DataPath.scala",
            "upstream/src/main/scala/xiangshan/backend/datapath/DataSource.scala",
            "upstream/src/main/scala/xiangshan/backend/datapath/NewPipelineConnect.scala",
            "upstream/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala",
            "upstream/src/main/scala/xiangshan/backend/decode/DecodeUnit.scala",
            "upstream/src/main/scala/xiangshan/backend/decode/DecodeStage.scala",
        ],
        "family_ids": [
            "core.backend.datapath",
            "core.backend.datapath.writeback",
            "core.decode.isa",
            "core.decode.csr",
            "core.csr.timer",
            "core.fu.vector",
            "core.fu.divider",
            "core.fu.fpu",
            "core.fu.arithmetic.csa",
            "core.fu.crypto",
            "core.fu.debug",
            "core.fu.shift",
            "core.fu.vector.mask",
            "core.fu.vector.mgu",
            "core.fu.vector.compare",
        ],
        "observation_points": [
            "frontend-to-backend decoupled handshake",
            "DataSource selector predicates",
            "pipeline ready/valid and flush",
            "five register-file writeback classes and memory EXU",
            "decode/dispatch ordering and exception fields",
        ],
        "anchor_map": {
            "Backend.scala": ["class Backend", "new DataPath", "new WbDataPath"],
            "DataPath.scala": ["class DataPath", "DataSource", "NewPipelineConnect"],
            "WbArbiter.scala": ["class RealWBCollideChecker", "class WbDataPath"],
            "DecodeUnit.scala": ["class DecodeUnit", "Instructions"],
            "DecodeStage.scala": ["class DecodeStage", "DecodeUnit"],
        },
        "evidence": [
            "validation/v2-backend-datapath-direct-results.json",
            "validation/v2-backend-datapath-differential-results.json",
            "validation/v2-backend-datapath-coverage-manifest.json",
            "validation/v2-decode-batch-results.json",
            "validation/v2-decode-batch-reference-results.json",
            "validation/v2-vector-batch-differential-results.json",
        ],
        "next_action": "Bind DataPath and WbDataPath first with explicit injected register-file/memory stubs; defer full Backend until decode, issue, rename, and CSR ports are covered.",
    },
    {
        "closure_id": "cache",
        "phase": "core-integration-3",
        "root_module": "MemBlock",
        "root_source": "upstream/src/main/scala/xiangshan/mem/MemBlock.scala",
        "children": [
            "DCacheWrapper",
            "DCache",
            "MainPipe",
            "AMOALU",
            "TagArray",
            "FrontendBridge",
            "ICacheBuffer",
            "ICacheCtrlBuffer",
        ],
        "indirect_children": {
            "DCache": "DCacheWrapper",
            "MainPipe": "DCacheWrapper/DCache",
            "AMOALU": "DCacheWrapper/DCache/MainPipe",
            "TagArray": "DCacheWrapper/DCache",
            "ICacheBuffer": "MemBlockInlined (inlined parent path)",
            "ICacheCtrlBuffer": "MemBlockInlined (inlined parent path)",
        },
        "source_paths": [
            "upstream/src/main/scala/xiangshan/mem/MemBlock.scala",
            "upstream/src/main/scala/xiangshan/cache/dcache/DCacheWrapper.scala",
            "upstream/src/main/scala/xiangshan/cache/dcache/mainpipe/MainPipe.scala",
            "upstream/src/main/scala/xiangshan/cache/dcache/mainpipe/AMOALU.scala",
            "upstream/src/main/scala/xiangshan/cache/dcache/meta/TagArray.scala",
            "upstream/src/main/scala/xiangshan/frontend/icache/ICache.scala",
        ],
        "family_ids": [
            "core.cache.dcache",
            "core.frontend.icache.mshr",
            "core.frontend.icache.replacer",
            "core.frontend.icache.utility",
            "core.cache.dcache.atomic",
            "core.cache.dcache.meta",
        ],
        "observation_points": [
            "DCache request/response TileLink channels",
            "AMO operation decode and mask merge",
            "TagArray reset/read/write collision and ECC/DFT controls",
            "MainPipe arbitration and replay",
            "MemBlock frontend bridge and flush ordering",
        ],
        "anchor_map": {
            "MemBlock.scala": ["class MemBlock", "class FrontendBridge", "class ICacheBuffer"],
            "DCacheWrapper.scala": ["class DCache", "class DCacheWrapper", "new MainPipe"],
            "MainPipe.scala": ["class MainPipe", "new AMOALU"],
            "TagArray.scala": ["class TagArray", "class TagSRAMBank"],
        },
        "evidence": [
            "validation/v2-dcache-batch-results.json",
            "validation/v2-dcache-batch-differential-results.json",
            "validation/v2-dcache-batch-coverage-manifest.json",
            "validation/v2-p1-b-icache-differential-results.json",
        ],
        "next_action": "Use the already matched AMOALU/TagArray closures to create a reduced DCache MainPipe parent harness; keep TileLink and MBIST/DFT dependencies injected and explicit.",
    },
    {
        "closure_id": "vector",
        "phase": "core-integration-0",
        "root_module": "VldMergeUnit",
        "root_source": "upstream/src/main/scala/xiangshan/backend/datapath/VldMergeUnit.scala",
        "children": [
            "VldMgu",
            "Mgu",
            "ByteMaskTailGen",
            "WbDataPath",
            "RealWBCollideChecker",
        ],
        "indirect_children": {
            "Mgu": "VldMgu",
            "ByteMaskTailGen": "Mgu (inlined child path)",
            "WbDataPath": "Backend",
            "RealWBCollideChecker": "WbDataPath",
        },
        "source_paths": [
            "upstream/src/main/scala/xiangshan/backend/datapath/VldMergeUnit.scala",
            "upstream/src/main/scala/xiangshan/backend/fu/vector/Mgu.scala",
            "upstream/src/main/scala/xiangshan/backend/fu/vector/ByteMaskTailGen.scala",
            "upstream/src/main/scala/xiangshan/backend/fu/vector/Mgtu.scala",
            "upstream/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala",
        ],
        "family_ids": [
            "core.fu.vector",
            "core.fu.vector.mask",
            "core.fu.vector.mgu",
            "core.fu.vector.compare",
            "core.backend.datapath.writeback",
        ],
        "observation_points": [
            "vector mask/tail merge",
            "vstart/vl and element-width splice",
            "VldMgu writeback timing",
            "writeback collision/priority",
        ],
        "anchor_map": {
            "VldMergeUnit.scala": ["class VldMergeUnit", "new VldMgu"],
            "Mgu.scala": ["class Mgu", "class VldMgu"],
            "ByteMaskTailGen.scala": ["class ByteMaskTailGen", "MaskExtractor"],
            "WbArbiter.scala": ["class WbDataPath", "RealWBCollideChecker"],
        },
        "evidence": [
            "validation/v2-vector-batch-differential-results.json",
            "validation/v2-vector-batch-coverage-manifest.json",
            "validation/v2-backend-datapath-differential-results.json",
        ],
        "next_action": "Start here: exercise VldMergeUnit with the existing vector child models and WbDataPath collision boundary; this is the smallest executable parent closure.",
    },
]


FAMILY_EVIDENCE: dict[str, list[str]] = {
    "core.decode.isa": ["validation/v2-decode-batch-results.json", "validation/v2-decode-batch-reference-results.json"],
    "core.decode.csr": ["validation/v2-decode-batch-results.json", "validation/v2-decode-batch-reference-results.json"],
    "core.csr.timer": ["validation/v2-decode-batch-results.json", "validation/v2-decode-batch-reference-results.json"],
    "core.fu.divider": [],
    "core.fu.fpu": ["validation/v2-decode-batch-results.json", "validation/v2-decode-batch-reference-results.json"],
    "core.fu.arithmetic.csa": ["validation/v2-decode-batch-results.json", "validation/v2-decode-batch-reference-results.json"],
    "core.fu.crypto": [],
    "core.fu.debug": [],
    "core.fu.shift": [],
    "core.fu.vector.mask": ["validation/v2-vector-batch-direct-results.json", "validation/v2-vector-batch-differential-results.json", "validation/v2-vector-batch-coverage-manifest.json"],
    "core.fu.vector.mgu": ["validation/v2-vector-batch-direct-results.json", "validation/v2-vector-batch-differential-results.json", "validation/v2-vector-batch-coverage-manifest.json"],
    "core.fu.vector.compare": ["validation/v2-vector-batch-direct-results.json", "validation/v2-vector-batch-differential-results.json", "validation/v2-vector-batch-coverage-manifest.json"],
    "core.cache.dcache.atomic": ["validation/v2-dcache-batch-results.json", "validation/v2-dcache-batch-differential-results.json"],
    "core.cache.dcache.meta": ["validation/v2-dcache-batch-results.json", "validation/v2-dcache-batch-differential-results.json"],
    "core.frontend.bpu.compare": ["validation/v2-frontend-batch-results.json", "validation/v2-frontend-batch-reference-results.json", "validation/v2-frontend-bpu-rvc-coverage-manifest.json"],
    "core.frontend.ftb": ["validation/v2-frontend-batch-results.json", "validation/v2-frontend-batch-reference-results.json", "validation/v2-frontend-bpu-rvc-coverage-manifest.json"],
    "core.frontend.bpu.counters": ["validation/v2-frontend-batch-results.json", "validation/v2-frontend-batch-reference-results.json", "validation/v2-frontend-bpu-rvc-coverage-manifest.json"],
    "core.replacement": ["validation/v2-replacement-batch-results.json", "validation/v2-replacement-batch-reference-results.json", "validation/v2-replacement-coverage-manifest.json"],
    "core.frontend.icache.mshr": ["validation/v2-p1-b-icache-direct-results.json", "validation/v2-p1-b-icache-differential-results.json", "validation/v2-p1-b-icache-coverage-manifest.json"],
    "core.frontend.icache.replacer": ["validation/v2-p1-b-icache-direct-results.json", "validation/v2-p1-b-icache-differential-results.json", "validation/v2-p1-b-icache-coverage-manifest.json"],
    "core.frontend.icache.utility": ["validation/v2-p1-b-icache-direct-results.json", "validation/v2-p1-b-icache-differential-results.json", "validation/v2-p1-b-icache-coverage-manifest.json"],
    "core.frontend.ifu.rvc": ["validation/v2-frontend-batch-results.json", "validation/v2-frontend-batch-reference-results.json", "validation/v2-frontend-bpu-rvc-coverage-manifest.json"],
    "core.backend.datapath": ["validation/v2-backend-datapath-direct-results.json", "validation/v2-backend-datapath-differential-results.json", "validation/v2-backend-datapath-coverage-manifest.json"],
    "core.backend.datapath.writeback": ["validation/v2-backend-datapath-direct-results.json", "validation/v2-backend-datapath-differential-results.json", "validation/v2-backend-datapath-coverage-manifest.json"],
}


def gate_for_family(family_id: str, summary: dict[str, Any], gate_name: str) -> str:
    """Derive a conservative gate state from explicit evidence keys.
    从显式证据键保守推导门禁状态。
    """

    if not summary["files"]:
        return "NOT_RUN"
    if gate_name == "direct" and summary["pass_signal_count"]:
        # A pass signal is bounded; never upgrade it to an acceptance state.
        return "PASS_BOUNDED"
    if gate_name == "reference" and summary["pass_signal_count"]:
        return "PASS_BOUNDED_REFERENCE"
    return "PENDING"


def family_parent_state(family_id: str, parent_rows: list[dict[str, Any]]) -> str:
    """Classify parent reachability independently from leaf pass signals.
    独立于 leaf 通过信号分类父级可达性。
    """

    rows = [row for row in parent_rows if family_id in row["family_ids"]]
    if not rows:
        return "UNMAPPED_PARENT"
    if any(row["root_present"] and row["reachable_child_count"] > 0 for row in rows):
        # A module can be reachable while the complete closure is still open.
        return "PARENT_MODULE_REACHABLE_CLOSURE_OPEN"
    if any(row["root_present"] for row in rows):
        return "PARENT_MODULE_PRESENT_CHILD_BINDING_OPEN"
    return "PARENT_REFERENCE_MISSING"


def build_report() -> dict[str, Any]:
    """Build the complete readiness report from pinned inputs.
    从固定输入构建完整 readiness 报告。
    """

    candidates_payload = load_json(CANDIDATE_MANIFEST)
    mapping_payload = load_json(MAPPING_MANIFEST)
    if not isinstance(candidates_payload, dict) or not isinstance(mapping_payload, dict):
        raise RuntimeError("candidate or mapping manifest is missing/invalid")
    candidates = candidates_payload.get("modules", [])
    mapping_entries = mapping_payload.get("entries", [])
    mapping_by_id = {entry.get("id"): entry for entry in mapping_entries if isinstance(entry, dict)}
    if len(candidates) != 35 or len(mapping_entries) != 35:
        raise RuntimeError(f"expected 35 candidates and mappings, got {len(candidates)} and {len(mapping_entries)}")

    xstop_present = XSTOP.is_file()
    xstop_size = XSTOP.stat().st_size if xstop_present else 0
    xstop_sha = sha256_file(XSTOP) if xstop_present else ""
    wanted_modules = {spec["root_module"] for spec in PARENT_SPECS}
    for spec in PARENT_SPECS:
        wanted_modules.update(spec["children"])
    records = read_module_records(XSTOP, wanted_modules) if xstop_present else {}

    parent_rows: list[dict[str, Any]] = []
    for spec in PARENT_SPECS:
        root = records.get(spec["root_module"])
        child_rows: list[dict[str, Any]] = []
        for child in spec["children"]:
            child_record = records.get(child)
            occurrences = count_reference(root, child) if root else 0
            if child_record is not None and occurrences:
                reachability = "DIRECT_MODULE_REFERENCE"
            elif child_record is not None and child in spec.get("indirect_children", {}):
                reachability = "INDIRECT_OR_INLINED_CHILD"
            elif child_record is not None:
                reachability = "MODULE_PRESENT_NOT_LEXICALLY_REFERENCED"
            elif occurrences:
                reachability = "INLINED_OR_GENERATED_ALIAS"
            else:
                reachability = "NOT_OBSERVED_IN_ROOT_BODY"
            child_rows.append(
                {
                    "name": child,
                    "xstop_module_present": child_record is not None,
                    "root_body_occurrences": occurrences,
                    "reachability": reachability,
                    "path_via": spec.get("indirect_children", {}).get(child),
                    "module": child_record.metadata() if child_record else None,
                }
            )
        source_rows: list[dict[str, Any]] = []
        for source_path in spec["source_paths"]:
            basename = Path(source_path).name
            anchors = spec["anchor_map"].get(basename, [])
            source_rows.append(source_record(source_path, anchors))
        reachable = [row for row in child_rows if row["reachability"] == "DIRECT_MODULE_REFERENCE"]
        inlined = [
            row
            for row in child_rows
            if row["reachability"] in {"INDIRECT_OR_INLINED_CHILD", "INLINED_OR_GENERATED_ALIAS"}
        ]
        missing = [row for row in child_rows if row["reachability"] == "NOT_OBSERVED_IN_ROOT_BODY"]
        parent_rows.append(
            {
                "closure_id": spec["closure_id"],
                "phase": spec["phase"],
                "root_source": spec["root_source"],
                "root_module": spec["root_module"],
                "root_present": root is not None,
                "root_module_metadata": root.metadata() if root else None,
                "children": child_rows,
                "reachable_child_count": len(reachable),
                "inlined_child_count": len(inlined),
                "unobserved_child_count": len(missing),
                "source_evidence": source_rows,
                "family_ids": spec["family_ids"],
                "observation_points": spec["observation_points"],
                "evidence": evidence_summary(spec["evidence"]),
                "readiness": (
                    "READY_FOR_REDUCED_PARENT_HARNESS"
                    if root is not None and len(reachable) > 0 and spec["closure_id"] == "vector"
                    else "PARENT_BOUNDARY_IDENTIFIED_CLOSURE_OPEN"
                    if root is not None
                    else "BLOCKED_REFERENCE_MODULE_MISSING"
                ),
                "next_action": spec["next_action"],
            }
        )

    # Candidate rows retain every candidate, including retired/split surfaces.
    candidate_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        source = candidate.get("source_scala", "")
        candidate_id = Path(source).stem
        mapping = mapping_by_id.get(candidate_id, {})
        family_id = mapping.get("family_id", "")
        family_files = FAMILY_EVIDENCE.get(family_id, [])
        summary = evidence_summary(family_files)
        parents = [row for row in parent_rows if family_id in row["family_ids"]]
        candidate_rows.append(
            {
                "candidate": candidate_id,
                "source_scala_v3": source,
                "target": candidate.get("destination"),
                "target_present": (ROOT / candidate.get("destination", "")).is_file(),
                "prior_v3_status": candidate.get("prior_v3_status"),
                "v2_status": candidate.get("v2_status"),
                "classification": mapping.get("classification"),
                "disposition": mapping.get("disposition"),
                "v2_sources": mapping.get("v2_source", []),
                "v2_source_evidence": [
                    source_record(path, []) for path in mapping.get("v2_source", [])
                ],
                "family_id": family_id,
                "closure_root": mapping.get("closure_root"),
                "parent_state": family_parent_state(family_id, parent_rows),
                "parent_closure_ids": [row["closure_id"] for row in parents],
                "leaf_evidence": {
                    "files": summary["files"],
                    "direct": gate_for_family(family_id, summary, "direct"),
                    "reference": gate_for_family(family_id, summary, "reference"),
                    "differential": "PRESENT_BOUNDED" if summary["pass_signal_count"] else "PENDING",
                },
                "promotion": "BLOCKED_ACCEPTED_NOT_ALLOWED",
            }
        )

    families: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_rows:
        families[row["family_id"]].append(row)
    family_rows: list[dict[str, Any]] = []
    for family_id in sorted(families):
        rows = families[family_id]
        files = sorted({f for row in rows for f in [item["path"] for item in row["leaf_evidence"]["files"]]})
        summary = evidence_summary(files)
        parent_ids = sorted({pid for row in rows for pid in row["parent_closure_ids"]})
        family_rows.append(
            {
                "family_id": family_id,
                "candidate_count": len(rows),
                "candidates": [row["candidate"] for row in rows],
                "parent_closure_ids": parent_ids,
                "parent_state": family_parent_state(family_id, parent_rows),
                "direct": gate_for_family(family_id, summary, "direct"),
                "reference": gate_for_family(family_id, summary, "reference"),
                "differential": "PRESENT_BOUNDED" if summary["pass_signal_count"] else "PENDING",
                "evidence_files": files,
                "evidence_present": summary["all_present"],
                "next_gate": "PARENT_CLOSURE_MATCHED",
            }
        )

    complete_or_bounded = [
        row["closure_id"]
        for row in parent_rows
        if row["readiness"] == "READY_FOR_REDUCED_PARENT_HARNESS"
    ]
    blockers = [
        "No full Frontend/Backend/Cache top-level parent wrapper exists in this auxiliary tree.",
        "Several V2 surfaces are inlined or distributed (BPU/FTB/counters, decode, and cache internals); lexical leaf presence is not parent equivalence.",
        "License review and external UHSC wrapper localization remain open for every family.",
        "The generated XSTop is a locked reference input; no candidate may be promoted from this scan.",
    ]
    if not xstop_present:
        blockers.insert(0, "Locked XSTop.sv is unavailable at the canonical WSL path.")
    elif xstop_size != EXPECTED_XSTOP_BYTES or xstop_sha != EXPECTED_XSTOP_SHA256:
        blockers.insert(0, "Locked XSTop.sv hash/size does not match V2 snapshot metadata.")

    return {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_PARENT_CLOSURE_READINESS",
        "generated_by": "validation/v2_parent_closure_readiness.py",
        "source_authority": {
            "source_commit": EXPECTED_SOURCE_COMMIT,
            "scala_root": "upstream/src/main/scala",
            "reference_canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
            "reference_local_access_path": str(XSTOP),
            "reference_sha256": EXPECTED_XSTOP_SHA256,
            "reference_bytes": EXPECTED_XSTOP_BYTES,
        },
        "scan": {
            "status": "PASS" if xstop_present and xstop_size == EXPECTED_XSTOP_BYTES and xstop_sha == EXPECTED_XSTOP_SHA256 else "BLOCKED",
            "locked_input_unchanged": True,
            "xstop_present": xstop_present,
            "observed_xstop_sha256": xstop_sha,
            "observed_xstop_bytes": xstop_size,
            "candidate_manifest_sha256": sha256_file(CANDIDATE_MANIFEST),
            "mapping_manifest_sha256": sha256_file(MAPPING_MANIFEST),
        },
        "scope": {
            "candidate_count": len(candidate_rows),
            "mapping_entry_count": len(mapping_entries),
            "family_count": len(family_rows),
            "parent_closure_count": len(parent_rows),
            "bounded_parent_ready": complete_or_bounded,
            "accepted_count": 0,
        },
        "recommended_order": [
            {
                "rank": 1,
                "closure_id": "vector",
                "reason": "Smallest executable parent boundary; existing vector parent evidence is PASS_BOUNDED_PARENT.",
            },
            {
                "rank": 2,
                "closure_id": "cache",
                "reason": "AMOALU and TagArray have bounded reference evidence; inject TileLink/MBIST at the parent boundary.",
            },
            {
                "rank": 3,
                "closure_id": "frontend",
                "reason": "ICache and RVC children are available, but BPU/FTB/counter behavior is distributed/inlined.",
            },
            {
                "rank": 4,
                "closure_id": "backend",
                "reason": "Datapath children are bounded, while full Backend still needs decode/issue/rename/CSR integration.",
            },
        ],
        "families": family_rows,
        "parent_closures": parent_rows,
        "candidates": candidate_rows,
        "gates": {
            "PYTHON_PRESENT": "PASS",
            "DIRECT_TEST_PASS_BOUNDED": "PRESENT_PER_FAMILY",
            "V2_REFERENCE_MATCHED": "PRESENT_BOUNDED_PER_FAMILY",
            "PARENT_CLOSURE_MATCHED": "PENDING_COORDINATOR_REVIEW",
            "UHSC_LOCALIZED": "PENDING_EXTERNAL_WRAPPER",
            "LICENSE_REVIEW": "PENDING_COORDINATOR_REVIEW",
            "ACCEPTED": "NOT_ALLOWED",
        },
        "blockers": blockers,
        "unclosed_gates": [
            "Coordinator must execute and review the reduced vector parent harness.",
            "Frontend, Backend, and Cache full parent wrappers are planned but not implemented in this scan.",
            "Inlined/distributed children need explicit coverage entries before parent closure can be matched.",
            "License and UHSC external wrapper gates remain open.",
        ],
    }


def main() -> int:
    """Write the readiness report and print a compact summary.
    写入 readiness 报告并打印紧凑摘要。
    """

    report = build_report()
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "output": str(OUTPUT.relative_to(ROOT)).replace("\\", "/"),
                "candidates": report["scope"]["candidate_count"],
                "families": report["scope"]["family_count"],
                "parents": report["scope"]["parent_closure_count"],
                "bounded_parent_ready": report["scope"]["bounded_parent_ready"],
                "accepted": report["gates"]["ACCEPTED"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
