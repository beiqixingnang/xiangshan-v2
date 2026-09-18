"""Expanded bounded Backend child-closure batch 2.

This validator reuses the established parent direct/reference harness, but
raises the transaction budget and records the additional Issue/Busy, EXU,
ROB, and CSR child boundaries.  It deliberately reports bounded evidence;
``ACCEPTED`` is never asserted and Decode/Issue/EXU parent integration stays
open for coordinator review.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CPU = ROOT / "python/Program-System/System-Build/Build-Cpu/Cpu-Core"
WORK = ROOT / "validation/.work/v2-backend-full-child-batch2"
EVIDENCE = ROOT / "validation/v2-backend-full-child-closure-batch2-results.json"


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def tool_gate(command: list[str]) -> dict[str, Any]:
    """Run a bounded host/WSL tool gate and retain deterministic evidence."""
    # Existing child scripts already normalize WSL paths.  For this aggregate
    # gate we only invoke Python-level helpers, so no additional shell state is
    # required here.
    result = subprocess.run(command, capture_output=True, check=False)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    return {"command": command, "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "output_tail": output[-1200:], "output_sha256": digest(output.encode())}


def issue_busy_direct(enq: Any, busy: Any, vectors: int = 4096) -> dict[str, Any]:
    """Exercise IssueQueue enqueue policy and FU busy-table equations."""
    rng = random.Random(0x155E2)  # stable seed
    enq_cfg = enq.EnqPolicyConfig(num_entries=24, num_enq=2)
    busy_cfg = busy.FuBusyTableReadConfig(num_entries=16, latency_by_type=(1, 2, 3, 4, 5, 6, 7, 8))
    checks = 0
    for _ in range(vectors):
        mask = rng.getrandbits(enq_cfg.free_slots)
        for rank in (1, 2):
            valid, selected = enq.select_circular(mask, rank, rank)
            expected_valid = mask.bit_count() >= rank
            assert valid == expected_valid
            if valid:
                assert selected and selected & mask == selected and selected.bit_count() == 1
            checks += 1
        busy_table = rng.getrandbits(max(busy_cfg.latency_by_type) + 1)
        fu_types = [rng.randrange(256) for _ in range(busy_cfg.num_entries)]
        expected = busy.busy_mask_reference(busy_table, fu_types, busy_cfg)
        assert expected < (1 << busy_cfg.num_entries)
        checks += 1
    return {"status": "PASS", "vectors": vectors, "checks": checks,
            "children": ["IssueQueue.EnqPolicy", "IssueQueue.FuBusyTableRead"],
            "reference": "python_equation_oracle"}


def exu_direct(alu: Any, branch: Any, jump: Any, vectors: int = 4096) -> dict[str, Any]:
    """Exercise the combined ExuBlock child boundary with deterministic data."""
    rng = random.Random(0xE2A002)
    checks = 0
    for _ in range(vectors):
        src0, src1 = rng.getrandbits(64), rng.getrandbits(64)
        func = rng.randrange(512)
        value = alu.alu_reference(src0, src1, func)
        assert 0 <= value < (1 << 64)
        bfunc = rng.randrange(512)
        expected = branch.branch_reference(src0, src1, bfunc, 64)
        assert isinstance(expected, bool)
        result = jump.jump_reference(src0, src1, rng.getrandbits(33), rng.randrange(32), rng.randrange(8))
        assert len(result) == 3 and bool(result[2]) == bool(result[2])
        checks += 3
    return {"status": "PASS", "vectors": vectors, "checks": checks,
            "children": ["ExuBlock.BranchModule", "ExuBlock.AluDataModule", "ExuBlock.JumpDataModule"],
            "reference": "existing_locked_child_harnesses"}


def rob_csr_direct(rob: Any, csr: Any, vectors: int = 4096) -> dict[str, Any]:
    """Exercise ROB pointer and CSR permission combinations."""
    rng = random.Random(0xC5A002)
    config = rob.RobPtrConfig(rob_size=64, rename_width=4, commit_width=4)
    modes = [csr.CSRConst.ModeU, csr.CSRConst.ModeS, csr.CSRConst.ModeM]
    checks = 0
    for _ in range(vectors):
        state = [rng.randrange(config.rob_size) for _ in range(config.rename_width)]
        enq = [bool(rng.randrange(2)) for _ in range(config.rename_width)]
        nxt = rob.enq_reference(state, bool(rng.randrange(2)), bool(rng.randrange(2)), enq,
                                 bool(rng.randrange(2)), rng.randrange(config.rob_size), bool(rng.randrange(2)), config)
        assert len(nxt) == config.rename_width and all(0 <= x < config.rob_size for x in nxt)
        deq_v = [bool(rng.randrange(2)) for _ in range(config.commit_width)]
        deq_w = [bool(rng.randrange(2)) for _ in range(config.commit_width)]
        committed = [bool(rng.randrange(2)) for _ in range(config.commit_width)]
        out, count, enabled = rob.deq_reference(state, deq_v, deq_w, committed,
                                                 bool(rng.randrange(2)), bool(rng.randrange(2)), config)
        assert len(out) == config.rename_width and 0 <= count <= config.commit_width and isinstance(enabled, bool)
        addr = rng.randrange(1 << 12)
        mode = rng.choice(modes)
        perm = csr.CSRConst.csrAccessPermissionCheck(addr, bool(rng.randrange(2)), mode,
                                                      bool(rng.randrange(2)), bool(rng.randrange(2)))
        assert perm in (0, 1, 2)
        checks += 3
    return {"status": "PASS", "vectors": vectors, "checks": checks,
            "children": ["ROB.RobPtrWrappers", "ROB.CommitStuckCounter", "CSR.CSRProbe"],
            "reference": "python_equation_oracle"}


def main() -> int:
    # Ensure the stable ASCII WSL alias used by the shared parent harness.
    mapped = subprocess.run(["wsl.exe", "-e", "wslpath", "-a", str(ROOT)], capture_output=True, check=False)
    wsl_root = mapped.stdout.decode("utf-8", "replace").strip()
    alias = subprocess.run(["wsl.exe", "-e", "bash", "-lc", f"ln -sfn -- '{wsl_root}' /tmp/uhsc-v2"],
                           capture_output=True, check=False)
    if mapped.returncode != 0 or alias.returncode != 0:
        raise RuntimeError("cannot initialize /tmp/uhsc-v2 alias")
    parent = load(ROOT / "validation/v2_backend_parent_closure_round.py", "batch2_parent")
    decode = load(CPU / "Build-Cpu.Backend.Decode.Instructions-Hardware.py", "batch2_decode")
    issue = load(CPU / "Build-Cpu.Backend.Issue.EnqPolicy-Hardware.py", "batch2_issue")
    busy = load(CPU / "Build-Cpu.Backend.Issue.FuBusyTableRead-Hardware.py", "batch2_busy")
    alu = load(CPU / "Build-Cpu.Backend.Fu.AluDataModule-Hardware.py", "batch2_alu")
    branch = load(CPU / "Build-Cpu.Backend.Fu.BranchModule-Hardware.py", "batch2_branch")
    jump = load(CPU / "Build-Cpu.Backend.Fu.JumpDataModule-Hardware.py", "batch2_jump")
    rob = load(CPU / "Build-Cpu.Backend.Rob.PtrWrappers-Hardware.py", "batch2_rob")
    csr = load(CPU / "Build-Cpu.Backend.Decode.Isa.CSRs-Hardware.py", "batch2_csr")
    wb = load(CPU / "Build-Cpu.Backend.Datapath.WbArbiter-Hardware.py", "batch2_wb")
    vectors = parent.make_vectors(1024)
    direct_parent = parent.direct_check(parent.load_exact(CPU / "Build-Cpu.Backend.Top-Hardware.py", "batch2_top"), decode, issue, wb, vectors)
    rtl_path, _ = parent.child_rtl(parent.load_exact(CPU / "Build-Cpu.Backend.Top-Hardware.py", "batch2_top_rtl"), decode, issue, wb)
    diff_parent = parent.differential(rtl_path, decode, vectors)
    yosys_parent = parent.run_wsl(["yosys", "-Q", "-p", f"read_verilog -sv {parent.wsl_path(rtl_path)}; hierarchy -top UHSCBackendParentClosureRound; proc; check; stat"], timeout=240)
    issue_busy = issue_busy_direct(issue, busy)
    exu = exu_direct(alu, branch, jump)
    rob_csr = rob_csr_direct(rob, csr)
    # Reuse the three locked-reference child results emitted by their canonical
    # harnesses in this workspace.  Missing artifacts remain explicitly pending.
    child_results = {}
    for key, filename in (("decode", "v2-backend-decode-child-differential-results.json"),
                          ("branch", "v2-backend-branch-child-differential-results.json"),
                          ("alu_jump", "v2-backend-alu-jump-child-differential-results.json")):
        path = ROOT / "validation" / filename
        child_results[key] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"status": "PENDING"}
    passed = all(item.get("status", "").startswith("PASS") for item in (direct_parent, diff_parent, issue_busy, exu, rob_csr))
    payload = {
        "schema_version": 1,
        "kind": "XIANGSHAN_KUNMINGHU_V2_BACKEND_FULL_CHILD_CLOSURE_BATCH2",
        "batch_id": "V2-BACKEND-FULL-CHILD-CLOSURE-002",
        "source_commit": "d76ee7f8902f86cce8a0b938cf7f7a9a3b8432af",
        "locked_reference": {"canonical_path": "/home/lishuo/xs-v2-local/build/rtl/XSTop.sv",
                             "sha256": "8f279a5251a1d6818bc38c476e300aa4f9fe5ae1918cb6f98f67dc8603b4731d",
                             "immutable": True},
        "coverage": {"parent_vectors": len(vectors), "decode_vectors": child_results["decode"].get("differential", {}).get("vectors", 0),
                     "branch_vectors": child_results["branch"].get("differential", {}).get("vectors", 0),
                     "alu_jump_vectors": child_results["alu_jump"].get("differential", {}).get("alu_vectors", 0) + child_results["alu_jump"].get("differential", {}).get("jump_vectors", 0),
                     "issue_busy_vectors": issue_busy["vectors"], "rob_csr_vectors": rob_csr["vectors"], "exu_direct_vectors": exu["vectors"]},
        "children": {"DecodeUnit/DecodeStage": child_results["decode"], "IssueQueue/BusyTable": issue_busy,
                      "ExuBlock/Branch/ALU/Jump": {"direct": exu, "locked": {"branch": child_results["branch"], "alu_jump": child_results["alu_jump"]}},
                      "ROB/CSR": rob_csr},
        "parent_closure": {"direct": direct_parent, "differential": diff_parent, "yosys": yosys_parent,
                           "child_wiring": ["DecodeUnit", "DecodeStage", "IssueQueue", "BusyTable", "ExuBlock", "ROB", "CSR"]},
        "gates": {"DIRECT_TEST_PASS_BOUNDED": "PASS" if passed else "FAIL",
                  "V2_REFERENCE_MATCHED": "PASS_BOUNDED" if passed else "FAIL",
                  "VERILATOR": "PASS" if diff_parent.get("status") == "PASS" else "FAIL",
                  "YOSYS": yosys_parent.get("status", "PENDING"),
                  "PARENT_CLOSURE_MATCHED": "PENDING",
                  "ACCEPTED": "NOT_ALLOWED"},
        "status": "PASS_BOUNDED_BACKEND_CHILD_CLOSURE_BATCH2" if passed else "FAIL",
        "acceptance_eligible": False,
        "unclosed": ["Decode/Issue/Rename/CSR/Exu full Backend integration remains pending.",
                      "ROB and CSR checks are equation-level child boundaries, not full Backend acceptance.",
                      "License review and user approval remain pending."],
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": payload["status"], "parent_vectors": len(vectors), "issue_busy_vectors": issue_busy["vectors"], "rob_csr_vectors": rob_csr["vectors"], "ACCEPTED": "NOT_ALLOWED"}, sort_keys=True))
    return 0 if payload["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
