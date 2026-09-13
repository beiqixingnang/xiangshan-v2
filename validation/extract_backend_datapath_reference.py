"""Extract V2 backend/datapath reference closures from locked XSTop.
从锁定的 XSTop 提取 V2 后端数据通路参考闭包。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
XSTOP = Path(r"\\wsl$\Debian\home\lishuo\xs-v2-local\build\rtl\XSTop.sv")
EXPECTED_SHA256 = "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d"
EXPECTED_BYTES = 228590583
OUT_DIR = ROOT / "validation" / "reference-closures"
INDEX = ROOT / "validation" / "v2-backend-datapath-reference-index.json"

MODULES = {
    "RealWBArbiter": "RealWBArbiter-v2.sv",
    "RealWBCollideChecker": "RealWBCollideChecker-v2.sv",
    # Specialization _25 retains the full ready/valid boundary while V2's
    # isOlder input is optimized to its default false at this parent site.
    "NewPipelineConnectPipe_25": "NewPipelineConnectPipe_25-v2.sv",
}


# Hash a file's exact bytes. / 对文件原始字节计算摘要。
def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Extract one complete module while preserving source bytes and line numbers.
# 提取完整模块并保留源字节与行号。
def extract_module(path: Path, name: str) -> tuple[bytes, int, int]:
    start_re = re.compile(rb"^module\s+" + re.escape(name.encode("ascii")) + rb"\s*\(")
    module_re = re.compile(rb"^module\s+")
    end_re = re.compile(rb"^endmodule\b")
    captured: list[bytes] = []
    start_line = 0
    depth = 0
    with path.open("rb") as stream:
        for line_number, line in enumerate(stream, 1):
            if depth == 0:
                if not start_re.match(line):
                    continue
                start_line = line_number
                depth = 1
                captured.append(line)
                continue
            captured.append(line)
            if module_re.match(line):
                depth += 1
            if end_re.match(line):
                depth -= 1
                if depth == 0:
                    return b"".join(captured), start_line, line_number
    raise RuntimeError(f"module {name} not found")


# Verify the locked artifact and write machine-readable extraction metadata.
# 校验锁定产物并写入机器可读提取元数据。
def main() -> int:
    if not XSTOP.is_file():
        raise FileNotFoundError(XSTOP)
    size = XSTOP.stat().st_size
    sha = digest(XSTOP)
    if size != EXPECTED_BYTES or sha != EXPECTED_SHA256:
        raise RuntimeError(f"locked XSTop mismatch: {size} {sha}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for module, filename in MODULES.items():
        payload, first, last = extract_module(XSTOP, module)
        destination = OUT_DIR / filename
        destination.write_bytes(payload)
        rows.append({
            "module": module,
            "path": destination.relative_to(ROOT).as_posix(),
            "sha256": digest(destination),
            "bytes": len(payload),
            "xstop_line_start": first,
            "xstop_line_end": last,
            "source_scala": "upstream/src/main/scala/xiangshan/backend/datapath/" + (
                "RFWBConflictChecker.scala" if module == "RealWBArbiter" else
                "WbArbiter.scala" if module == "RealWBCollideChecker" else
                "NewPipelineConnect.scala"
            ),
            "interface_mode": "extractable_module",
        })
    payload = {
        "schema_version": 1,
        "kind": "V2_P1_D_BACKEND_DATAPATH_REFERENCE_EXTRACTION",
        "batch_id": "V2-P1-D-BACKEND-DATAPATH",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "xstop": {"canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
                  "local_access_path": str(XSTOP), "sha256": sha, "bytes": size},
        "modules": rows,
        "source_level_surfaces": [
            {"module": "DataSource", "source": "upstream/src/main/scala/xiangshan/backend/datapath/DataSource.scala",
             "mode": "source_equation_parent_closure", "observation_points": ["value[3]", "eight selector equalities"]},
            {"module": "WbDataPath", "source": "upstream/src/main/scala/xiangshan/backend/datapath/WbArbiter.scala",
             "mode": "source_parent_closure", "observation_points": ["int/fp/vf/v0/vl arbitration", "memory EXU inclusion", "uncertain-latency ready"]},
        ],
        "extraction": "PASS",
        "locked_input_unchanged": True,
        "acceptance_eligible": False,
    }
    INDEX.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8", newline="\n")
    print(json.dumps({"modules": len(rows), "xstop_sha256": sha}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
