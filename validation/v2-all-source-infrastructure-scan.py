#!/usr/bin/env python3
"""Generate the reviewed 873-file infrastructure planning fragment.

This tool reads the current all-source seed and tracked Scala sources, verifies
their exact path set and SHA-256 values, then writes only the owned scan JSON.
It does not inspect locked references as a classification authority and never
changes a Build, master mapping, progress record, or source file.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


AUXILIARY_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = AUXILIARY_ROOT.parents[1]
SEED_PATH = AUXILIARY_ROOT / "validation" / "v2-all-source-scan-seed.json"
OUTPUT_PATH = AUXILIARY_ROOT / "validation" / "v2-all-source-infrastructure-scan.json"
SCOPE_ROOTS = (
    "upstream/rocket-chip",
    "upstream/chisel3",
    "upstream/macros",
)
EXPECTED_ROOT_COUNTS = {
    "upstream/rocket-chip": 350,
    "upstream/chisel3": 522,
    "upstream/macros": 1,
}
SCOPE_CLAIM = "ALL_SOURCE_PLANNED_NOT_IMPLEMENTED"


def build_path(directory: str, feature: str) -> str:
    """Return a complete auxiliary Build path with its direct-parent prefix."""
    return (
        "python/Program-System/System-Build/Build-Cpu/"
        f"{directory}/{directory}-{feature}-Hardware.py"
    )


TARGETS: dict[str, dict[str, Any]] = {
    "rocket_protocol": {
        "path": build_path("Cpu-Core", "Dependency.Rocket.Protocol"),
        "responsibility": (
            "Complete generic ready-valid and bus protocol families: TileLink, "
            "AXI4, AXIS, AHB and APB records, adapters, monitors, buffers, "
            "crossbars, register routers, address/source translation and "
            "channel arbitration. The current candidate is only a reuse point; "
            "this plan includes every source configuration and optional family."
        ),
        "required_configuration_modes": [
            "TileLink A-D channel widths, beat size, source/sink IDs, request ordering, FIFO domains, and legal opcode sets",
            "AXI4 address/data/id/user widths, burst lengths, outstanding transaction counts, credits, and ordering",
            "AXIS payload, sideband widths, packet boundaries, and stream buffering",
            "AHB and APB transfer widths, wait-state behavior, error response, and register-router address maps",
            "buffer depth, flow-through/pipe modes, arbitration policy, and reset behavior",
            "all enabled and currently unused protocol adapters and peripheral nodes",
        ],
        "dependencies": ["rocket_diplomacy", "clock_reset", "utility_pipeline"],
    },
    "rocket_diplomacy": {
        "path": build_path("Cpu-Core", "Dependency.Rocket.Diplomacy"),
        "responsibility": (
            "Pure configuration and graph semantics for address sets/ranges, "
            "transfer/id ranges, resource bindings, node edges, lazy module "
            "resolution, and address decoding. Implement only the consumed "
            "Python-standard-library configuration model, not the full Scala "
            "configuration library."
        ),
        "required_configuration_modes": [
            "address base/mask/range legality and overlap policy",
            "transfer sizes, source/sink ID ranges, and manager/client parameters",
            "resource bindings, aliases, references, and device-tree values",
            "lazy node graph edge ordering, parameters-at-site/up/down, and graph closure",
            "bus topology and every declared enabled or unused configuration option",
        ],
        "dependencies": ["rocket_protocol", "clock_reset", "rocket_core"],
    },
    "rocket_hardfloat": {
        "path": build_path("Cpu-Core", "Dependency.Rocket.Hardfloat"),
        "responsibility": (
            "Parameterized floating-point recoding, classification, compare, "
            "integer/float conversion, add/multiply/FMA, divide/square-root, "
            "rounding, flags, and exceptional values."
        ),
        "required_configuration_modes": [
            "legal exponent/significand widths and recoded/IEEE representations",
            "rounding modes, tininess policy, invalid/overflow/underflow/inexact flags",
            "signed and unsigned integer conversion widths and saturation/exception cases",
            "all divide/square-root iteration and special-value branches",
        ],
        "dependencies": ["utility_bits"],
    },
    "rocket_jtag": {
        "path": build_path("Cpu-Core", "Dependency.Rocket.Jtag"),
        "responsibility": (
            "JTAG TAP and debug transport, DMI request/response sequencing, "
            "debug ROM contents/configuration, system-bus access, and reset/"
            "busy/error behavior."
        ),
        "required_configuration_modes": [
            "TAP instruction width, IDCODE, reset/startup state, and scan register lengths",
            "DMI address/data widths, request/response backpressure, busy and failure responses",
            "debug ROM selection/content, abstract command and system-bus access modes",
            "debug enabled/disabled and asynchronous reset behavior",
        ],
        "dependencies": ["rocket_protocol", "clock_reset", "rocket_core"],
    },
    "rocket_tl_children": {
        "path": build_path("Cpu-Core", "Dependency.Rocket.TLChildren.Family"),
        "responsibility": (
            "Reusable TileLink cache-child and address/data adapters, including "
            "coherence/probe handling, bank binding, width conversion, "
            "fragmentation, FIFOFixer and hint handling. Reuse is a planning "
            "candidate and does not close unlisted family members."
        ),
        "required_configuration_modes": [
            "coherence states, probe/ack permissions, and transaction ordering",
            "beat widths, bank count, source remapping, fragment size, and FIFO domains",
            "flow/pipe buffering, hints, atomic operations, and error propagation",
        ],
        "dependencies": ["rocket_protocol", "rocket_diplomacy", "utility_pipeline"],
    },
    "utility": {
        "path": build_path("Cpu-Core", "Dependency.Utility"),
        "responsibility": (
            "Existing shared arithmetic/bit/ECC/pointer utility candidate. "
            "Expand its planned V2 ownership only where the source behavior "
            "matches these functions; presence of the candidate grants no "
            "implementation or verification credit."
        ),
        "required_configuration_modes": [
            "bit and pointer widths, power-of-two and wraparound cases",
            "parity and SECDED code width, syndrome, corrected data, and double-error reporting",
            "saturating/wrapping performance counters and event enable conditions",
            "all documented legal source counts and boundary indices",
        ],
        "dependencies": ["utility_bits", "utility_state"],
    },
    "utility_bits": {
        "path": build_path("Cpu-Core", "Dependency.Utility.BitSelectFamily"),
        "responsibility": (
            "Combinational bit selection, compression/extraction, barrel "
            "shifts, one-hot and priority selection, decode-table comparison, "
            "prefix operations, and truth-table lookup."
        ),
        "required_configuration_modes": [
            "input/output widths, bit masks, sign/zero extension, and legal shift amounts",
            "priority order and default/fallback behavior for every mux table",
            "decoder field values, don't-care masks, and overlapping-match policy",
            "empty, singleton, maximum-width, and sparse/dense prefix inputs",
        ],
        "dependencies": [],
    },
    "utility_delay": {
        "path": build_path("Cpu-Core", "Dependency.Utility.DelayFamily"),
        "responsibility": (
            "Fixed-cycle delay and reset/enable/valid gated pipeline registers, "
            "including flushable pipeline fields and their exact latency."
        ),
        "required_configuration_modes": [
            "delay length, payload field width, and reset value",
            "plain, valid-gated, enable-gated, and flushable modes",
            "flush, redirect, replay, reset polarity, and arbitrary startup state",
        ],
        "dependencies": ["utility_pipeline", "clock_reset"],
    },
    "utility_pipeline": {
        "path": build_path("Cpu-Core", "Dependency.Utility.PipelineFamily"),
        "responsibility": (
            "Ready-valid queues, elastic pipeline stages, enqueue/dequeue "
            "handshake, flow/pipe behavior, ordering, occupancy, and backpressure."
        ),
        "required_configuration_modes": [
            "queue depth including zero/one/multiple entries and legal bounds",
            "flow-through, pipe, flush, bypass, and registered-ready modes",
            "payload width/fields, enqueue/dequeue simultaneous transfer, and reset",
            "ordering, occupancy, full/empty, and backpressure at each boundary",
        ],
        "dependencies": ["chisel_decoupled", "chisel_arbiter", "clock_reset"],
    },
    "utility_residual": {
        "path": build_path("Cpu-Core", "Dependency.Utility.ResidualFamily"),
        "responsibility": (
            "Explicit remaining leaf family for ID allocation, clock-gating "
            "wrappers, selected LFSR utilities, carry-save logic, and other "
            "named combinational/control modules. Each member must retain its "
            "own observed behavior."
        ),
        "required_configuration_modes": [
            "ID pool size, allocation/release collision and exhaustion behavior",
            "LFSR polynomial, width, seed, and maximal-period corner cases",
            "clock-gate enable/test-enable and reset behavior",
            "compressor widths, carry alignment, and boundary propagation",
        ],
        "dependencies": ["utility_bits", "utility_state", "clock_reset"],
    },
    "chisel_arbiter": {
        "path": build_path("Cpu-Core", "Dependency.Chisel.Arbiter"),
        "responsibility": (
            "Generic locking and non-locking arbiters, fixed and round-robin "
            "priority, winner retention, locking beat counts, grants/readies, "
            "and decoupled arbitration."
        ),
        "required_configuration_modes": [
            "input count, fixed/round-robin policy, and legal minimum bounds",
            "priority direction, lock mode, beat count, and winner hold conditions",
            "valid/ready combinations, simultaneous requests, no-request, and reset",
        ],
        "dependencies": ["chisel_decoupled", "utility_pipeline"],
    },
    "chisel_decoupled": {
        "path": build_path("Cpu-Core", "Dependency.Chisel.Decoupled"),
        "responsibility": (
            "ReadyValid/Decoupled/Irrevocable interfaces and generic Chisel "
            "Queue hardware, including flush, flow-through, pipe, occupancy, "
            "ordering, and backpressure. The interface declarations themselves "
            "may use Amaranth records; queue equations remain a real target."
        ),
        "required_configuration_modes": [
            "queue depth, flow, pipe, flush, and synchronization options",
            "payload record shape and valid/ready state transitions",
            "empty/full behavior, simultaneous enqueue/dequeue, and reset",
        ],
        "dependencies": ["chisel_arbiter", "utility_pipeline", "clock_reset"],
    },
    "icache_replacer": {
        "path": build_path("Cpu-Core", "Frontend.Icache.ICacheReplacer"),
        "responsibility": (
            "Replacement-policy state and victim selection, including true/"
            "pseudo LRU, sequence/random policies, update priority, and reset."
        ),
        "required_configuration_modes": [
            "set/way count, legal associativity, and replacement policy selection",
            "access/update order, invalid-way preference, tie breaking, and reset state",
            "random replacement seed/polynomial where used",
        ],
        "dependencies": ["utility_state", "utility_bits"],
    },
    "csr": {
        "path": build_path("Cpu-Core", "Backend.Decode.Isa.CSRs"),
        "responsibility": (
            "CSR address/field declarations, privilege and read/write masks, "
            "reset values, side effects, and static CSR configuration."
        ),
        "required_configuration_modes": [
            "supported privilege/extension configuration and CSR address legality",
            "field reset values, writable/read-only masks, and read/write side effects",
            "trap, debug, interrupt, counter, and custom CSR enable modes",
        ],
        "dependencies": ["rocket_core", "clock_reset"],
    },
    "rocket_core": {
        "path": build_path("Cpu-Core", "Dependency.ProcessorFamily"),
        "responsibility": (
            "Complete Rocket-family processor/tile/system behavior: fetch, "
            "decode, execution, privilege/CSR, RoCC, debug, interrupt, tile "
            "assembly, integrated I/D caches, TLB/PTW, and all legal/unused "
            "configuration modes."
        ),
        "required_configuration_modes": [
            "core width, privilege/extensions, branch predictor, and pipeline parameters",
            "FPU, multiplier, RoCC/custom instruction, debug, and interrupt enable modes",
            "tile count, hart IDs, bus attachments, reset vectors, and optional devices",
            "all defaults and legal constructor bounds, including currently unused configurations",
        ],
        "dependencies": [
            "rocket_protocol", "rocket_diplomacy", "rocket_jtag",
            "rocket_hardfloat", "clock_reset", "utility_state",
        ],
    },
    "clock_reset": {
        "path": build_path("Cpu-Core", "Dependency.ClockResetFamily"),
        "responsibility": (
            "Clock/reset/interrupt crossings and synchronizers: synchronous, "
            "rational, asynchronous and credited crossings; Gray-pointer async "
            "queues; reset catch/stretch/wrangling; interrupt source/sink and "
            "crossbar state. Preserve domain and reset assumptions."
        ),
        "required_configuration_modes": [
            "synchronous/rational/asynchronous/credited crossing and safe/narrow options",
            "clock ratio, queue depth, Gray pointer width, reset isolation and initial state",
            "async assert/sync deassert, reset polarity, stretch length, and synchronizer depth",
            "interrupt source/sink ranges, priority, routing, masks, and pending-state reset",
        ],
        "dependencies": ["rocket_diplomacy", "rocket_protocol", "utility_pipeline"],
    },
    "utility_state": {
        "path": build_path("Cpu-Core", "Dependency.Utility.StateFamily"),
        "responsibility": (
            "Generic stateful utility families across vendored sources: "
            "counters/timers, random/LFSR/PRNG state, ECC/CRC/S-box coding, "
            "memory/SRAM/ROM access, reorder/ID/replacement state, and "
            "state-transition helpers not owned by a protocol or cache family."
        ),
        "required_configuration_modes": [
            "counter width, wrap/saturate, enable, clear, compare, and boundary conditions",
            "LFSR/PRNG width, polynomial, seed, tap order, and zero/period behavior",
            "ECC/CRC code family, data width, syndrome, correction, and error-reporting cases",
            "memory depth/width, read/write latency, masks, initialization, and collision semantics",
            "replacement/ID-pool capacity, allocation/release priority, and reset state",
        ],
        "dependencies": ["utility_bits", "utility_pipeline", "clock_reset"],
    },
}


HARDWARE_CATEGORIES = {"HARDWARE_BEHAVIOR", "MIXED_HARDWARE_SUPPORT"}
TEST_PATH_PARTS = (
    "/src/test/",
    "/tests/",
    "/integration-tests/",
    "/svsimTests/",
    "/chiselTests/",
    "/firrtlTests/",
)
TEST_FILE = re.compile(r"(?:Test|Tests|Tester|Spec)\.scala$", re.IGNORECASE)
CONFIG_NAME = re.compile(
    r"(?:Config|Params?|Parameters|Key|Field|Port|Bundle|Range|Protocol|Options|AttachParams)$"
)
DEFINITION_PATTERN = re.compile(
    r"(?m)^\s*(?:(?:override|private\[[^\]]+\]|protected)\s+)*def\s+([A-Za-z_][A-Za-z0-9_]*)"
)
STATE_PATTERN = re.compile(
    r"\b(?:val|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=\n]+)?=\s*"
    r"[^,\n]*(RegInit|RegNext|RegEnable|SyncReadMem|Mem|Counter|Queue|Reg)\b"
)
REQUIRE_PATTERN = re.compile(r"(?m)^\s*(?:require|assert)\s*\([^\n]*")
CONTROL_PATTERN = re.compile(
    r"\b(?:PriorityMux|RRArbiter|LockingArbiter|RoundRobin|winner|grant|priority|"
    r"when|elsewhen|otherwise|switch)\b|^\s*case\s+(?!class\b|object\b|trait\b)"
)


def make_route(
    classification: str,
    target_ids: list[str],
    reason: str,
    obligations: list[str],
    declaration_disposition: str,
) -> dict[str, Any]:
    """Create a single reviewed route result."""
    if classification not in {
        "HARDWARE_BEHAVIOR",
        "ELABORATION_CONFIG",
        "HOST_TOOL",
        "TEST_ONLY",
        "DECLARATION_SUPPORT",
        "MIXED_HARDWARE_SUPPORT",
    }:
        raise ValueError(f"Unknown source classification: {classification}")
    unknown_targets = [key for key in target_ids if key not in TARGETS]
    if unknown_targets:
        raise ValueError(f"Unknown target identifiers: {unknown_targets}")
    return {
        "classification": classification,
        "target_ids": target_ids,
        "reason": reason,
        "obligations": obligations,
        "declaration_disposition": declaration_disposition,
    }


def target_route(
    classification: str,
    target_id: str,
    reason: str,
    obligations: list[str],
    declaration_disposition: str = "PRIMARY_OWNER",
) -> dict[str, Any]:
    """Route one source family to its primary Build owner."""
    return make_route(
        classification,
        [target_id],
        reason,
        obligations,
        declaration_disposition,
    )


def test_route(reason: str) -> dict[str, Any]:
    """Record a source whose only purpose is a test or executable example."""
    return make_route(
        "TEST_ONLY",
        [],
        reason,
        ["Retain as source/test provenance only; it is not a product RTL Build."],
        "TEST_ONLY",
    )


def host_route(reason: str) -> dict[str, Any]:
    """Record compiler, backend, simulator, or host utility code."""
    return make_route(
        "HOST_TOOL",
        [],
        reason,
        [
            "Preserve any needed output options as explicit Python configuration.",
            "Do not translate the compiler, emitter, native binding, or simulator implementation into RTL.",
        ],
        "HOST_TOOL_ONLY",
    )


def declaration_route(reason: str) -> dict[str, Any]:
    """Record language/API declarations supplied by native Amaranth semantics."""
    return make_route(
        "DECLARATION_SUPPORT",
        [],
        reason,
        [
            "Use Amaranth's native values, records, modules, memories, clocks, and reset semantics.",
            "Do not create a one-to-one Scala language/compiler Build for declaration-only APIs.",
        ],
        "AMARANTH_OR_STDLIB_SUPPORT",
    )


def source_is_test(path: str) -> bool:
    """Identify explicitly test-only trees, names, and the Chisel CI sample."""
    lowered = f"/{path.lower()}/"
    if any(part in lowered for part in TEST_PATH_PARTS):
        return True
    if path.endswith(".github/workflows/build-scala-cli-example/chisel-example.scala"):
        return True
    if TEST_FILE.search(path.rsplit("/", 1)[-1]):
        return True
    if path.startswith("upstream/rocket-chip/src/main/scala/") and any(
        f"/{name}/" in lowered for name in ("groundtest", "unittest", "formal")
    ):
        return True
    if path.startswith("upstream/chisel3/src/main/scala/") and any(
        f"/{name}/" in lowered for name in ("cookbook", "examples")
    ):
        return True
    return False


def classify_chisel(path: str, seed_row: dict[str, Any]) -> dict[str, Any]:
    """Apply reviewed Chisel language/compiler versus hardware-helper boundaries."""
    if source_is_test(path):
        return test_route(
            "Chisel test/spec/fixture/cookbook or CI compile example; the module "
            "exercises the language/API or another tested component and is not "
            "an independently maintained processor Build."
        )

    if path.startswith("upstream/chisel3/binder/"):
        return host_route(
            "Binder code converts Chisel data and FIRRTL/CIRCT representations "
            "for a compiler backend; Amaranth replaces the output-language "
            "semantics, so this native binding layer is not RTL."
        )
    if path.startswith("upstream/chisel3/macros/") or path.startswith(
        "upstream/chisel3/plugin/"
    ):
        return host_route(
            "Scala compiler macro/plugin implementation performs compile-time "
            "rewrites and source naming; port only the resulting hardware "
            "behavior through Python/Amaranth APIs."
        )
    if path.startswith("upstream/chisel3/svsim/"):
        return host_route(
            "SV simulation workspace/backend/runner code manages host compilers, "
            "processes, and workspaces; it has no product RTL behavior."
        )
    if path.startswith("upstream/chisel3/project/"):
        return host_route(
            "Build-project version/release/dependency declarations configure "
            "the Scala toolchain and do not define hardware."
        )
    if path.startswith("upstream/chisel3/firrtl/src/main/scala/firrtl/ir/"):
        return declaration_route(
            "FIRRTL IR declarations describe compiler syntax trees and types. "
            "The planned Build uses Amaranth-native hardware values rather than "
            "reimplementing FIRRTL as an RTL compiler."
        )
    if path.startswith("upstream/chisel3/firrtl/") or path.startswith(
        "upstream/chisel3/circt/"
    ) or path.startswith("upstream/chisel3/logger/"):
        if "/options/" in path or "Options" in path or "Annotation" in path:
            return make_route(
                "ELABORATION_CONFIG",
                [],
                "Compiler/stage/logger option and annotation declarations are "
                "host configuration for FIRRTL/CIRCT; preserve only explicit "
                "Python options that affect emitted design selection.",
                [
                    "Map selected top, pass options, output paths, and memory-image inputs to explicit Python configuration.",
                    "Do not recreate the Scala phase manager, parser, logger, or emitter as hardware.",
                ],
                "PYTHON_HOST_CONFIGURATION",
            )
        return host_route(
            "FIRRTL/CIRCT/logger phases, transforms, parser, emitter, and "
            "serialization code are compiler host tools; Amaranth/Yosys provides "
            "the planned RTL language and export path."
        )
    if path.startswith("upstream/chisel3/src/main/scala/chisel3/util/"):
        return classify_chisel_utility(path, seed_row)
    if path.startswith("upstream/chisel3/src/main/scala/chisel3/stage/"):
        return make_route(
            "ELABORATION_CONFIG",
            [],
            "Chisel stage and command-line option files select elaboration, "
            "top modules, transforms, and output destinations; only the "
            "explicitly used values become Python configuration.",
            [
                "Preserve selected top/configuration, enabled transforms, and output-format choices as plain Python fields.",
                "Do not port Stage/Phase execution or CLI parsing into RTL.",
            ],
            "PYTHON_HOST_CONFIGURATION",
        )
    if path.startswith("upstream/chisel3/src/main/scala/chisel3/"):
        if any(token in path for token in ("/internal/plugin/", "/internal/panama/", "/simulator/", "/testers/")):
            return host_route(
                "Chisel source macro, native CIRCT bridge, simulator, or tester "
                "implementation is a host execution tool, not hardware behavior."
            )
        if "/internal/" in path or "/experimental/" in path or "/aop/" in path:
            return declaration_route(
                "Chisel internal/experimental/AOP declarations implement DSL "
                "construction, naming, reflection, or aspect hooks. Their "
                "hardware meaning is expressed directly through Amaranth, not "
                "by porting the Scala compiler mechanism."
            )
        return declaration_route(
            "Chisel Data/Bundle/Module/Clock/Reset/Mem and related language "
            "declarations are the source DSL. Amaranth supplies these native "
            "construction semantics; hardware helpers under chisel3.util are "
            "mapped separately."
        )

    return host_route(
        "This Chisel source lies in compiler/runtime support outside the "
        "hardware-helper subtree; preserve only a concrete selected Python "
        "configuration value if a family consumes it."
    )


def classify_chisel_utility(
    path: str, seed_row: dict[str, Any]
) -> dict[str, Any]:
    """Map Chisel utility hardware helpers to complete behavioral families."""
    suffix = path.split("/src/main/scala/chisel3/util/", 1)[1]
    stem = suffix.rsplit("/", 1)[-1].removesuffix(".scala")

    if stem == "Arbiter":
        return target_route(
            "MIXED_HARDWARE_SUPPORT",
            "chisel_arbiter",
            "Arbiter.scala defines generic Chisel arbitration and locking "
            "hardware together with ready/valid declaration helpers. Preserve "
            "the state and equations for every generic family member.",
            [
                "Implement fixed-priority, round-robin, locking and non-locking selection, grants, per-input ready, and winner hold.",
                "Preserve lock beat counter update/clear priority, no-request behavior, and all legal arbiter input-count bounds.",
                "Expose interface records through Amaranth while retaining actual arbitration equations.",
            ],
        )
    if stem == "Decoupled":
        return target_route(
            "MIXED_HARDWARE_SUPPORT",
            "chisel_decoupled",
            "Decoupled.scala combines ready-valid interface declarations with "
            "real Queue/flush/flow/pipe hardware. The interface may be native "
            "Amaranth data; queue state and handshakes remain executable RTL.",
            [
                "Implement Queue, QueueIO, Decoupled and Irrevocable state transitions, occupancy, full/empty and transfer conditions.",
                "Preserve enqueue/dequeue simultaneous-transfer priority, flow-through, pipe, flush, reset and legal depth branches.",
                "Keep valid/ready/payload propagation observable for every declared generic configuration.",
            ],
        )
    if suffix.startswith("random/"):
        return target_route(
            "HARDWARE_BEHAVIOR",
            "utility_state",
            "The Chisel random utility source contains hardware LFSR/PRNG state "
            "and/or transition equations; it is not a Scala compiler feature.",
            [
                "Preserve register width, tap polynomial, shift/XOR direction, seed, and zero-state behavior.",
                "Retain output selection and state-advance enable priority for each LFSR/PRNG variant.",
                "Keep maximal-period and legal-width parameter branches explicit.",
            ],
        )

    if stem in {"Valid", "Reg"}:
        target_id = "utility_pipeline" if stem == "Valid" else "utility_delay"
        return target_route(
            "HARDWARE_BEHAVIOR",
            target_id,
            f"{stem}.scala defines valid pipeline/delay register hardware and "
            "must retain latency, enable, and reset behavior.",
            [
                "Preserve each valid/data state register, enable condition, reset value, and cycle latency.",
                "Retain input/output ready-valid or shift-register field ordering and legal depth branches.",
            ],
        )

    if suffix.startswith("circt/"):
        if stem == "ClockGate":
            return target_route(
                "MIXED_HARDWARE_SUPPORT",
                "clock_reset",
                "The ClockGate intrinsic wraps a real clock-gating function; "
                "host intrinsic registration is support, while enable/test "
                "semantics are hardware.",
                [
                    "Preserve gate enable, test enable, clock propagation, and reset behavior.",
                    "Keep technology-independent behavior in Amaranth and treat intrinsic naming as adapter metadata.",
                ],
            )
        if stem == "Synthesis":
            return target_route(
                "MIXED_HARDWARE_SUPPORT",
                "utility_bits",
                "Synthesis cell helpers include combinational mux cells and "
                "backend declarations; preserve the mux equations and express "
                "them as Amaranth logic.",
                [
                    "Preserve Mux2/Mux4 select encoding, input ordering, and default branch.",
                    "Do not require CIRCT-specific intrinsic lowering for ordinary combinational behavior.",
                ],
            )
        if stem in {"IsX", "LTLIntrinsics", "PlusArgsTest", "PlusArgsValue", "SizeOf"}:
            return declaration_route(
                f"{stem}.scala declares a CIRCT-specific verification, simulation, "
                "or elaboration intrinsic, not a generic processor RTL primitive. "
                "Use native assertions/configuration only where a concrete target "
                "family requires the same observable contract."
            )

    if suffix.startswith("experimental/decode/"):
        if stem in {"decoder", "DecoderBundle", "TruthTable", "DecodeTableAnnotation"}:
            return target_route(
                "MIXED_HARDWARE_SUPPORT",
                "utility_bits",
                "The decode-table family combines truth-table/declaration "
                "configuration with generated Boolean hardware. Preserve all "
                "table fields and use Amaranth equations for the decoder.",
                [
                    "Preserve decode fields, row ordering, match/miss behavior, and overlapping-pattern priority.",
                    "Treat Espresso/QMC minimization as an elaboration optimization; the unminimized truth table must retain identical outputs.",
                    "Retain selected-bit masks, wildcard/don't-care semantics, and legal field widths.",
                ],
            )
        return make_route(
            "ELABORATION_CONFIG",
            ["utility_bits"],
            "Decoder minimizers and truth-table helpers are host-side generation "
            "support whose output table affects hardware. The Python family "
            "keeps the table/configuration contract and emits native Amaranth "
            "logic instead of porting a Scala compiler algorithm.",
            [
                "Preserve exact truth-table rows, don't-care values, field widths, and selected decode result.",
                "Do not require Espresso executable discovery or a Scala minimizer at Build import/elaboration time.",
            ],
            "PYTHON_CONFIGURATION_OWNER",
        )

    if stem in {
        "Bitwise", "Cat", "BitPat", "CircuitMath", "Lookup", "Math",
        "Mux", "OneHot", "Enum", "pla", "PrefixSum", "BarrelShifter",
    }:
        return target_route(
            "MIXED_HARDWARE_SUPPORT",
            "utility_bits",
            f"{stem}.scala supplies combinational bit, selection, encoding, "
            "or table semantics used by generated hardware.",
            [
                "Preserve operand order, width/signedness, selected bit indices, and empty/singleton boundary behavior.",
                "Retain selector/match priority, default output and out-of-range handling.",
                "Keep only host-side constants as configuration; realize output behavior in Amaranth equations.",
            ],
        )

    if stem in {
        "Counter", "GrayCode", "MixedVec", "SparseVec", "SRAM",
    }:
        return target_route(
            "HARDWARE_BEHAVIOR",
            "utility_state",
            f"{stem}.scala defines generic state, address, or memory hardware "
            "that remains in scope independently of whether the locked CPU "
            "instance uses every configuration.",
            [
                "Preserve state/register/memory shape, reset/initialization, and read/write ordering.",
                "Retain legal width/depth/index bounds and simultaneous access/collision behavior.",
                "Preserve all branch choices that affect count, address, occupancy, or selected data.",
            ],
        )

    if stem == "LoadMemoryTransform":
        return make_route(
            "ELABORATION_CONFIG",
            ["utility_state"],
            "Load-memory annotations and transforms carry memory image/init "
            "configuration. The image contents and initialization contract are "
            "inputs to the memory family; Scala transform/file-writer code is "
            "not RTL.",
            [
                "Preserve image format, address/data widths, initialization order, and absent-image behavior.",
                "Represent selected memory images as explicit configuration/artifacts, never as a product-time source scanner.",
            ],
            "PYTHON_CONFIGURATION_OWNER",
        )

    if stem in {
        "BlackBoxUtils", "ExtModuleUtils", "BoringUtils", "ForceNames",
        "getAnnotations", "Inline", "Conditional", "ImplicitConversions",
    }:
        return declaration_route(
            f"{stem}.scala is a black-box/resource, naming, cross-module "
            "elaboration, annotation, or DSL-control support API. It is not a "
            "standalone hardware family; any consumed signal behavior is "
            "represented by explicit Build interfaces/configuration."
        )

    markers = set(seed_row.get("hardware_markers", []))
    if markers:
        return target_route(
            "MIXED_HARDWARE_SUPPORT",
            "utility_state",
            f"{stem}.scala is under the Chisel utility source tree and carries "
            f"hardware constructs {', '.join(sorted(markers))}; conservatively "
            "retain the full source family rather than exclude it by marker or lock status.",
            [
                "Preserve all declared module/IO/state/memory behavior and parameter branches from this source.",
                "Use native Amaranth records for declaration-only members but keep observed equations and state transitions.",
            ],
        )

    return declaration_route(
        f"{stem}.scala contributes utility declarations or compile-time "
        "construction support but has no independent hardware state/equations; "
        "its behavior is represented by the receiving Amaranth family APIs."
    )


def classify_rocket(path: str, seed_row: dict[str, Any]) -> dict[str, Any]:
    """Apply reviewed Rocket-Chip/hardfloat/config and generic family boundaries."""
    if source_is_test(path):
        return test_route(
            "Scala test, Tester, ground-test, formal, or unit-test harness; "
            "retain the fixture and its scenarios in test provenance, not as a "
            "production hardware Build."
        )

    if path.startswith("upstream/rocket-chip/cde/"):
        return make_route(
            "ELABORATION_CONFIG",
            ["rocket_diplomacy"],
            "CDE Field/View/Parameters/Config implement a generic host-side "
            "configuration graph. Replace only required keys, defaults, "
            "composition and lookup with explicit standard-library Python "
            "records; do not port CDE one class at a time.",
            [
                "Preserve key defaults, override order, view/site/up lookup, and missing-key behavior.",
                "Retain only the exact bus/core/device configuration fields consumed by the planned families.",
                "Keep configuration values serializable and explicit; do not scan the Scala tree at runtime.",
            ],
            "PYTHON_CONFIGURATION_OWNER",
        )
    if path.startswith("upstream/rocket-chip/hardfloat/"):
        return target_route(
            "HARDWARE_BEHAVIOR",
            "rocket_hardfloat",
            "Hardfloat conversion/arithmetic source defines actual parameterized "
            "floating-point behavior; absence of lexical Chisel markers in "
            "pure bit algorithms does not make it non-hardware.",
            [
                "Preserve recoded exponent/significand layout, canonical NaN, infinities, zeros, subnormals, and signaling-NaN cases.",
                "Retain arithmetic rounding, guard/round/sticky bits, flags, overflow/underflow, divide-by-zero, and illegal-width branches.",
                "Keep every legal expWidth/sigWidth specialization and conversion direction.",
            ],
        )
    if path.startswith("upstream/rocket-chip/macros/"):
        return host_route(
            "Rocket macro/ValName code generates source names at Scala "
            "compile-time; preserve a required public label as explicit "
            "configuration, not as an RTL implementation."
        )

    relative = path.split("upstream/rocket-chip/src/main/scala/", 1)[-1]
    filename = path.rsplit("/", 1)[-1]
    stem = filename.removesuffix(".scala")
    lowered = relative.lower()

    if relative.startswith("util/"):
        return classify_rocket_utility(path, stem, seed_row)

    if relative.startswith("prci/") or relative.startswith("interrupts/"):
        classification = "ELABORATION_CONFIG" if not seed_row.get("hardware_markers") else "MIXED_HARDWARE_SUPPORT"
        return target_route(
            classification,
            "clock_reset",
            "PRCI/interrupt sources define clock/reset domains, crossing "
            "parameters, synchronizers, interrupt source/sink routing, or "
            "crossbar behavior. This scope includes every mode, not only the "
            "locked CPU configuration.",
            [
                "Preserve domain clock/reset connections, asynchronous assertion, synchronous deassertion, and synchronizer stage count.",
                "Retain crossing choice (sync/rational/async/credited), reset-safe queue behavior, and Gray-pointer state.",
                "Preserve interrupt source/sink ranges, priority, masks, pending state, and reset/update ordering.",
            ],
            "CONFIGURATION_OWNER" if classification == "ELABORATION_CONFIG" else "PRIMARY_OWNER",
        )

    if relative.startswith("amba/"):
        if "crossing" in stem.lower() or stem in {"AsyncCrossing", "RationalCrossing"}:
            return target_route(
                "MIXED_HARDWARE_SUPPORT",
                "clock_reset",
                "AMBA clock/reset crossing helper combines protocol-shaped "
                "records with CDC/reset behavior; the clock-domain family "
                "owns the crossing state while the protocol family owns the "
                "ordinary channel contract.",
                [
                    "Preserve all AXI/AXIS/AHB/APB channel fields through each crossing.",
                    "Retain synchronizer/async queue depth, reset isolation, and backpressure across clock domains.",
                ],
            )
        if any(token in stem for token in ("Parameters", "Protocol", "Bundles", "Nodes")) or stem == "package":
            return target_route(
                "DECLARATION_SUPPORT",
                "rocket_protocol",
                "AMBA parameter, bundle, protocol, package, and node declarations "
                "define the full bus ABI and legal elaboration modes; expose "
                "them as explicit Python configuration/Amaranth records while "
                "keeping the associated protocol hardware family in scope.",
                [
                    "Retain AXI4/AXIS/AHB/APB field names, widths, directions, sidebands, and optional fields.",
                    "Preserve legal beat/address/id widths, burst/transfer modes, and protocol parameter constraints.",
                    "Do not restrict interface families to modules present in the locked XSTop.",
                ],
                "PRIMARY_OWNER",
            )
        return target_route(
            "HARDWARE_BEHAVIOR",
            "rocket_protocol",
            "AMBA source implements bus transfer, adapter, monitor, buffering, "
            "crossbar, register-router, SRAM bridge, or error behavior.",
            [
                "Preserve valid/ready or HREADY/HRESP transfer conditions, channel ordering, burst/beat count, and error response.",
                "Retain arbitration priority, outstanding-transaction storage, reset/flush, byte masks, and backpressure.",
                "Keep every AXI4, AXIS, AHB and APB source/configuration family, including unused variants.",
            ],
        )

    if relative.startswith("tilelink/"):
        if stem in {
            "AsyncCrossing", "RationalCrossing", "CrossingHelper",
            "BlockDuringReset",
        }:
            return target_route(
                "MIXED_HARDWARE_SUPPORT",
                "clock_reset",
                "TileLink crossing/reset helper combines TL channel declarations "
                "with clock-domain or reset control; retain the transfer protocol "
                "and crossing state together.",
                [
                    "Preserve TileLink A-D fields, request/response ordering, and valid/ready propagation across the crossing.",
                    "Retain clock ratio, synchronizer, async queue, reset-safe and reset-blocking behavior.",
                ],
            )
        if stem in {
            "AtomicAutomata", "Broadcast", "CacheCork", "FIFOFixer",
            "Fragmenter", "HintHandler", "ProbePicker", "RAMModel",
            "RegionReplication", "SRAM", "SourceShrinker", "WidthWidget",
            "AddressAdjuster",
        }:
            classification = "MIXED_HARDWARE_SUPPORT" if seed_row.get("hardware_markers") else "ELABORATION_CONFIG"
            return target_route(
                classification,
                "rocket_tl_children",
                f"{stem}.scala implements or configures a TileLink cache/memory "
                "child, coherence, miss/refill, bank, address, width, fragment, "
                "or source-ID function.",
                [
                    "Preserve cache/coherence state, probe/acquire/release priority, miss/refill ordering, and error branches.",
                    "Retain legal beat/bank/source-ID bounds, address transforms, fragment widths, and width conversion.",
                    "Keep SRAM/RAM depth, latency, byte masks, and read/write collision semantics when present.",
                ],
                "PRIMARY_OWNER",
            )
        if stem in {"Fuzzer", "PatternPusher", "ErrorEvaluator", "RegisterRouterTest"}:
            return test_route(
                f"{stem}.scala generates traffic or checks protocol behavior for tests; "
                "its vectors belong in tests and do not form a production protocol endpoint."
            )
        if any(token in stem for token in ("Parameters", "Bundles", "Nodes", "Edges")) or stem == "package":
            return target_route(
                "DECLARATION_SUPPORT",
                "rocket_protocol",
                "TileLink parameter, bundle, node, edge, and package declarations "
                "define the generic channel ABI and transfer/legal-width "
                "configuration consumed by the protocol family.",
                [
                    "Preserve TileLink A-B-C-D-E channel fields, opcodes, source/sink widths, and bundle direction.",
                    "Retain manager/client transfer-size, FIFO-domain, region, and legal source-range configuration.",
                    "Keep all generic parameter modes even where the locked CPU specializes them away.",
                ],
            )
        return target_route(
            "HARDWARE_BEHAVIOR",
            "rocket_protocol",
            f"{stem}.scala implements TileLink arbitration, buffering, crossbar, "
            "monitor, adapter, error, or transaction behavior.",
            [
                "Preserve A-D channel handshake, source tracking, beat locking, arbitration priority, and response routing.",
                "Retain buffer occupancy, queue order, flow/pipe behavior, reset/flush, and outstanding-request state.",
                "Keep protocol parameter checks and unused TileLink adapters in the family closure.",
            ],
        )

    if relative.startswith("devices/debug/") or relative.startswith("jtag/"):
        return target_route(
            "MIXED_HARDWARE_SUPPORT" if seed_row.get("hardware_markers") else "DECLARATION_SUPPORT",
            "rocket_jtag",
            "Debug/JTAG sources define TAP scan and debug transport, DMI/SBA "
            "request-response behavior, debug control, or the associated "
            "interface/ROM configuration.",
            [
                "Preserve TAP state transitions, scan shift order, instruction selection, reset, and IDCODE behavior.",
                "Retain DMI busy/error responses, request/response backpressure, SBA address/data/control state, and debug enable modes.",
                "Preserve debug ROM content selection and all optional debug configuration values.",
            ],
            "PRIMARY_OWNER",
        )

    if relative.startswith("diplomacy/"):
        if stem in {"ClockNodes", "ClockParameters", "ClockDomain", "ClockGroup", "ResetSynchronizer", "ResetWrangler"}:
            return target_route(
                "MIXED_HARDWARE_SUPPORT" if seed_row.get("hardware_markers") else "ELABORATION_CONFIG",
                "clock_reset",
                f"{stem}.scala defines clock/reset node parameters, domain wiring, "
                "synchronization, or reset coordination.",
                [
                    "Preserve clock/reset node graph edges, frequency/phase parameters, and reset polarity.",
                    "Retain reset synchronization, source/sink connection and all supported domain configurations.",
                ],
                "PRIMARY_OWNER",
            )
        if stem in {"LazyModule", "Nodes"}:
            return target_route(
                "MIXED_HARDWARE_SUPPORT",
                "rocket_diplomacy",
                f"{stem}.scala owns the lazy graph/node elaboration boundary "
                "and contributes real module/interface realization to parent "
                "hardware families. The source declarations are shared graph "
                "support, while each receiving hardware family retains its own "
                "RTL behavior.",
                [
                    "Preserve node input/output ordering, parameter propagation, binding and edge resolution.",
                    "Retain module/IO realization, clone/adapter behavior, graph closure, and all connected child interfaces.",
                    "Treat locked module names as scope annotations only; they do not prove this graph support or any child Build implemented.",
                ],
            )
        classification = "HARDWARE_BEHAVIOR" if "AddressDecoder" in stem else "ELABORATION_CONFIG"
        return target_route(
            classification,
            "rocket_diplomacy",
            f"{stem}.scala defines diplomacy address/range/resource/node graph "
            "semantics or the address decoder; convert only consumed graph and "
            "configuration operations to standard Python plus actual Amaranth "
            "decode behavior.",
            [
                "Preserve address mask/range containment, overlap and decode priority.",
                "Retain node parameter propagation and graph ordering for lazy modules.",
                "Preserve resource alias/reference/binding behavior and all required defaults.",
            ],
            "PRIMARY_OWNER" if classification == "HARDWARE_BEHAVIOR" else "PYTHON_CONFIGURATION_OWNER",
        )

    if relative.startswith("regmapper/"):
        return target_route(
            "MIXED_HARDWARE_SUPPORT" if seed_row.get("hardware_markers") else "ELABORATION_CONFIG",
            "rocket_protocol",
            "Register mapper descriptions/configuration feed actual bus register "
            "read/write hardware, masks, read actions, and side effects.",
            [
                "Preserve address decode, field widths, byte masks, read/write permissions, and reset values.",
                "Retain read-clear/read-set/write-one behavior, arbitration, response timing, and error branches.",
                "Map serializer/description metadata to Python configuration only where externally observable.",
            ],
            "PRIMARY_OWNER",
        )

    if relative.startswith("devices/tilelink/"):
        if stem in {"CLINT", "ClockBlocker", "Plic"}:
            return target_route(
                "MIXED_HARDWARE_SUPPORT",
                "clock_reset",
                f"{stem}.scala implements timer/interrupt/clock control behavior "
                "and configuration; preserve its real register and pending state.",
                [
                    "Retain timer compare/counter state, interrupt pending/enable/priority, and reset/update order.",
                    "Preserve clock-block enable and backpressure or gating conditions.",
                ],
            )
        if stem in {"BootROM", "MaskROM", "TestRAM"}:
            if stem == "TestRAM":
                return test_route("TestRAM.scala is a zero-delay simulation/test memory model, not a product memory.")
            return target_route(
                "MIXED_HARDWARE_SUPPORT",
                "rocket_tl_children",
                f"{stem}.scala defines memory-mapped ROM behavior and its address/content configuration.",
                [
                    "Preserve address range, byte/word alignment, ROM image/content, response latency, and unmapped/error behavior.",
                    "Keep all configured ROM variants as explicit immutable inputs.",
                ],
            )
        if stem in {"PhysicalFilter", "BusBlocker", "BusBypass", "MasterMux", "Error", "Deadlock", "DevNull", "Zero"}:
            return target_route(
                "HARDWARE_BEHAVIOR" if seed_row.get("hardware_markers") else "DECLARATION_SUPPORT",
                "rocket_protocol",
                f"{stem}.scala implements or declares a TileLink device, filter, "
                "blocker, master mux, null/error responder, or deadlock monitor.",
                [
                    "Preserve request admission/block conditions, address/permission checks, response routing, and error/zero data.",
                    "Retain reset, registered state, and exact ready/valid/response timing.",
                ],
            )
        return target_route(
            "MIXED_HARDWARE_SUPPORT" if seed_row.get("hardware_markers") else "ELABORATION_CONFIG",
            "rocket_core",
            f"{stem}.scala contributes optional system device parameters or "
            "module attachment behavior to the complete processor/tile system family.",
            [
                "Preserve optional-device selection, attachment order, bus location, address range, interrupt connection, and reset mode.",
                "Keep default and currently unused configuration branches explicit.",
            ],
            "PRIMARY_OWNER",
        )

    if relative.startswith("rocket/"):
        if stem in {
            "DCache", "HellaCache", "HellaCacheArbiter", "ICache",
            "NBDcache", "PTW", "TLB", "TLBPermissions",
            "SimpleHellaCacheIF", "ScratchpadSlavePort",
        }:
            return target_route(
                "HARDWARE_BEHAVIOR",
                "rocket_core",
                f"{stem}.scala defines cache, translation, page walk, replay, "
                "or scratchpad behavior; these families remain in scope even "
                "when their locked configuration is specialized.",
                [
                    "Preserve tag/data/mask arrays, hit/miss/refill/replay/flush priority, and outstanding-request state.",
                    "Retain page-level, ASID/VMID, permission, page-fault, and PTW walk branches.",
                    "Keep reset, error/ECC, arbitration, replacement, and exact response latency.",
                ],
            )
        classification = "ELABORATION_CONFIG" if stem in {
            "Instructions", "Instructions32", "CustomInstructions", "Consts", "package"
        } else "HARDWARE_BEHAVIOR"
        return target_route(
            classification,
            "rocket_core",
            f"{stem}.scala defines Rocket-family instruction/configuration or "
            "actual fetch/decode/execute/CSR/debug/control hardware.",
            [
                "Preserve instruction match order, illegal/default branches, RV32/RV64 legality, privilege, and extension configuration.",
                "Retain pipeline valid/ready/flush, exception/redirect priority, register/CSR state, and operation latency.",
                "Keep ALU/bit-manipulation/crypto, multiplier, branch predictor, breakpoint, and custom-instruction behavior where present.",
            ],
            "PYTHON_CONFIGURATION_OWNER" if classification == "ELABORATION_CONFIG" else "PRIMARY_OWNER",
        )

    if relative.startswith("tile/"):
        if stem in {"L1Cache"}:
            return target_route(
                "MIXED_HARDWARE_SUPPORT",
                "rocket_core",
                "L1Cache.scala declares and configures Rocket cache structures used by the memory family.",
                [
                    "Preserve cache sets/ways/line size, tag/data/ECC structure, and legal associativity branches.",
                    "Retain cache bus parameters, address ranges, and replacement configuration.",
                ],
            )
        if stem in {"TilePRCIDomain", "Interrupts"}:
            return target_route(
                "MIXED_HARDWARE_SUPPORT",
                "clock_reset",
                f"{stem}.scala wires tile reset/clock or interrupt inputs and state.",
                [
                    "Preserve tile clock/reset domain connections, interrupt synchronization and priority.",
                    "Retain reset/update ordering and all optional interrupt source branches.",
                ],
            )
        return target_route(
            "MIXED_HARDWARE_SUPPORT" if seed_row.get("hardware_markers") else "ELABORATION_CONFIG",
            "rocket_core",
            f"{stem}.scala defines core/tile parameters, RoCC interface/control, "
            "FPU/control, bus-error handling, or tile assembly.",
            [
                "Preserve RoCC command/response ready-valid, custom opcode fields, and outstanding state.",
                "Retain core/tile parameter bounds, hart ID, bus attachment, interrupt/debug connections, and reset vector.",
                "Keep FPU exception/rounding control and tile error reporting where present.",
            ],
            "PRIMARY_OWNER",
        )

    if relative.startswith("subsystem/") or relative.startswith(
        "system/"
    ) or relative.startswith("examples/"):
        return target_route(
            "MIXED_HARDWARE_SUPPORT" if seed_row.get("hardware_markers") else "ELABORATION_CONFIG",
            "rocket_core",
            f"{stem}.scala defines system/tile/bus topology, top-level hardware "
            "attachment, or a legal example-system configuration.",
            [
                "Preserve front/system/periphery/control/memory bus topology and node attachment order.",
                "Retain default/alternate configs, tile counts, crossings, debug/JTAG, interrupt, RTC, memory and reset options.",
                "Keep example hardware behavior mapped; only test suites are TEST_ONLY.",
            ],
            "PRIMARY_OWNER",
        )

    if relative:
        markers = seed_row.get("hardware_markers", [])
        if markers:
            return target_route(
                "MIXED_HARDWARE_SUPPORT",
                "rocket_core",
                f"{stem}.scala is an unclassified Rocket source with hardware "
                f"constructs {', '.join(markers)}. Conservatively retain it "
                "under the processor/system family until a reviewed narrower "
                "family is identified.",
                [
                    "Preserve all state, port, priority, reset, and configuration branches observed in the source.",
                    "Do not infer non-hardware status from empty lock-module lists or sparse lexical markers.",
                ],
            )
        return target_route(
            "DECLARATION_SUPPORT",
            "rocket_diplomacy",
            f"{stem}.scala is a non-RTL Rocket configuration/interface declaration "
            "with no source hardware markers; map its consumed values to the "
            "standard-library diplomacy/configuration model rather than omit it.",
            [
                "Preserve declared parameter names/defaults and resource/interface shape where consumed.",
                "Do not create a one-to-one Scala config library or infer that the declaration is implemented.",
            ],
            "PYTHON_CONFIGURATION_OWNER",
        )

    return make_route(
        "MIXED_HARDWARE_SUPPORT",
        ["rocket_core"],
        "Unresolved Rocket-Chip source is conservatively retained as mixed "
        "hardware support pending focused ownership review.",
        [
            "Preserve all functions, state, storage, priorities, and legal configuration branches observed in the source.",
            "Do not exclude based on absent lexical markers or locked-reference membership.",
        ],
        "PRIMARY_OWNER",
    )


def classify_rocket_utility(
    path: str, stem: str, seed_row: dict[str, Any]
) -> dict[str, Any]:
    """Map Rocket generic utility sources by actual state/bit/queue/clock duties."""
    if stem in {
        "AsyncQueue", "AsyncResetReg", "ClockDivider", "ClockGate",
        "Crossing", "RationalCrossing", "ResetCatchAndSync", "ShiftReg",
        "SynchronizerReg",
    }:
        return target_route(
            "MIXED_HARDWARE_SUPPORT",
            "clock_reset",
            f"{stem}.scala defines clock-domain crossing, reset, synchronizer, "
            "clock-gate, or associated parameter records.",
            [
                "Preserve synchronizer depth, async/sync reset polarity, initial values, Gray-pointer stages, and metastability boundary assumptions.",
                "Retain safe/narrow crossing choices, reset reconvergence, clock enable/test-enable, and exact domain latency.",
            ],
        )
    if stem in {
        "Arbiters",
    }:
        return target_route(
            "HARDWARE_BEHAVIOR",
            "chisel_arbiter",
            "Generic Rocket arbitration source defines locking, peeking, "
            "counting and in-order arbitration state and priority.",
            [
                "Preserve fixed/round-robin priority, winner lock, beat counter, and release condition.",
                "Retain request/response ordering and the route queue state for in-order mode.",
                "Keep legal input-count and lock-count parameter checks.",
            ],
        )
    if stem in {
        "HellaQueue", "LanePositionedQueue", "MultiLaneQueue",
        "MultiPortQueue", "MultiWidthFifo", "ReorderQueue", "ShiftQueue",
        "Broadcaster", "Repeater", "CreditedIO", "LatencyPipe",
    }:
        return target_route(
            "MIXED_HARDWARE_SUPPORT",
            "utility_pipeline",
            f"{stem}.scala defines a generic queue, FIFO, broadcast, repeat, "
            "credit or latency-pipeline family.",
            [
                "Preserve enqueue/dequeue pointers, occupancy, wraparound, full/empty and simultaneous transfer priority.",
                "Retain payload lane/port/width ordering, memory/register storage choice, and read/write latency.",
                "Keep flow/pipe/flush/credit configuration and all backpressure branches.",
            ],
        )
    if stem in {"BarrelShifter", "Misc", "MuxLiteral", "PrefixSum", "ReduceOthers"}:
        return target_route(
            "MIXED_HARDWARE_SUPPORT",
            "utility_bits",
            f"{stem}.scala implements generic combinational selection, shift, "
            "mux or prefix logic, potentially with elaboration-time configuration.",
            [
                "Preserve operand and lane ordering, signedness, bit widths, and shift amount handling.",
                "Retain priority/fallback/default branches and exact carry/prefix equations.",
                "Keep all supported widths and empty/singleton legal cases.",
            ],
        )
    if stem == "Replacement":
        return target_route(
            "HARDWARE_BEHAVIOR",
            "icache_replacer",
            "Replacement.scala contains random, sequence, true-LRU, pseudo-LRU "
            "and set-associative victim-selection state.",
            [
                "Preserve update and invalid-way priority, victim tie-breaking, tree/stack state, and reset.",
                "Retain set/way parameter constraints and random seed/polynomial behavior.",
                "Keep every policy variant even when only one locked cache mode is selected.",
            ],
        )
    if stem in {
        "ECC", "CRC", "SBox", "LCG", "Counters", "Timer", "SeededRandom",
        "DescribedSRAM", "IDPool", "ROMGenerator", "ScatterGather",
    }:
        target_id = "utility" if stem in {"ECC", "IDPool"} else "utility_state"
        return target_route(
            "HARDWARE_BEHAVIOR",
            target_id,
            f"{stem}.scala defines a real generic state/coding/memory "
            "primitive; retain its full legal configuration and state behavior.",
            [
                "Preserve source state registers, initialization/reset, enable/clear, and update priority.",
                "Retain coding polynomial/table/width, memory depth/latency/masks, or allocation capacity as applicable.",
                "Keep all legal parameter bounds and error/overflow/underflow branches.",
            ],
        )
    if stem in {"Annotations", "GeneratorUtils", "PlusArg", "Property"}:
        return host_route(
            f"{stem}.scala records annotations, compiler-generated artifacts, "
            "command-line plus-arguments, or verification properties; it is "
            "host/test support rather than product RTL."
        )
    if stem in {"Frequency", "BundleMap", "GenericParameterizedBundle", "HeterogeneousBag", "Location", "RecordMap", "SimpleProduct"}:
        return target_route(
            "ELABORATION_CONFIG",
            "rocket_diplomacy",
            f"{stem}.scala supplies parameter/bundle/location/map declarations "
            "for host-side elaboration and graph configuration.",
            [
                "Preserve consumed type/field shape, key lookup, ordering and default values as standard Python records.",
                "Do not port unused Scala collection/reflection machinery.",
            ],
            "PYTHON_CONFIGURATION_OWNER",
        )
    if stem in {"CoreMonitor", "TraceCoreInterface", "PSDTestMode"}:
        return target_route(
            "MIXED_HARDWARE_SUPPORT",
            "rocket_core",
            f"{stem}.scala declares processor trace/monitor/test-mode interfaces "
            "and associated observable signals.",
            [
                "Preserve public field widths/directions, counter/event selection and sampling enable.",
                "Retain trace type, instruction, hart, reset and test-mode propagation.",
            ],
        )
    if seed_row.get("hardware_markers"):
        return target_route(
            "MIXED_HARDWARE_SUPPORT",
            "utility_state",
            f"{stem}.scala is a generic utility source containing "
            f"{', '.join(seed_row['hardware_markers'])}; retain it conservatively "
            "even when it lacks a historical family mapping.",
            [
                "Preserve actual state/storage elements, update/clear priority, and all observed hardware branches.",
                "Retain constructor parameter constraints and queue/memory/counter legal modes.",
            ],
        )
    return target_route(
        "DECLARATION_SUPPORT",
        "rocket_diplomacy",
        f"{stem}.scala is generic type/configuration support for Rocket utility "
        "families and is represented with standard-library configuration rather "
        "than a new RTL implementation.",
        [
            "Preserve consumed field names, defaults, ordering and type constraints.",
            "Do not classify this source as implemented solely because it is assigned to a candidate family.",
        ],
        "PYTHON_CONFIGURATION_OWNER",
    )


def classify_source(path: str, seed_row: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one exact tracked Scala source to its reviewed classification."""
    if path.startswith("upstream/chisel3/"):
        return classify_chisel(path, seed_row)
    if path.startswith("upstream/rocket-chip/"):
        return classify_rocket(path, seed_row)
    if path == "upstream/macros/src/main/scala/CSRMacros.scala":
        return target_route(
            "DECLARATION_SUPPORT",
            "csr",
            "CSRMacros.scala expands CSR field declarations at Scala compile "
            "time; its macro mechanism is not hardware. The resulting CSR names, "
            "addresses, masks, reset values and side effects belong to the CSR "
            "Python configuration/build family.",
            [
                "Preserve each generated CSR field/address/mask/default and ordering.",
                "Replace macro expansion with explicit Python declarations; do not embed Scala or generate code at Build import time.",
            ],
            "PRIMARY_OWNER",
        )
    raise ValueError(f"Source outside the owned infrastructure slice: {path}")


def strip_scala_comments(source_text: str) -> str:
    """Mask nested Scala comments while preserving strings and line positions."""
    output: list[str] = []
    index = 0
    block_depth = 0
    string_delimiter = ""
    escaped = False
    line_comment = False
    while index < len(source_text):
        pair = source_text[index : index + 2]
        triple = source_text[index : index + 3]
        char = source_text[index]

        if line_comment:
            if char == "\n":
                output.append("\n")
                line_comment = False
            else:
                output.append(" ")
            index += 1
            continue

        if block_depth:
            if pair == "/*":
                output.extend((" ", " "))
                block_depth += 1
                index += 2
            elif pair == "*/":
                output.extend((" ", " "))
                block_depth -= 1
                index += 2
            else:
                output.append("\n" if char == "\n" else " ")
                index += 1
            continue

        if string_delimiter:
            if string_delimiter == '"""':
                if triple == '"""':
                    output.extend(('"', '"', '"'))
                    string_delimiter = ""
                    index += 3
                else:
                    output.append(char)
                    index += 1
            elif escaped:
                output.append(char)
                escaped = False
                index += 1
            elif char == "\\":
                output.append(char)
                escaped = True
                index += 1
            elif char == string_delimiter:
                output.append(char)
                string_delimiter = ""
                index += 1
            else:
                output.append(char)
                index += 1
            continue

        if triple == '"""':
            output.extend(('"', '"', '"'))
            string_delimiter = '"""'
            index += 3
        elif char in {'"', "'"}:
            output.append(char)
            string_delimiter = char
            index += 1
        elif pair == "//":
            output.extend((" ", " "))
            line_comment = True
            index += 2
        elif pair == "/*":
            output.extend((" ", " "))
            block_depth = 1
            index += 2
        else:
            output.append(char)
            index += 1
    return "".join(output)


def extract_guard_calls(source_text: str, function_name: str) -> list[str]:
    """Extract complete balanced require/assert expressions from source text."""
    clean_text = strip_scala_comments(source_text)
    matches = list(re.finditer(rf"\b{re.escape(function_name)}\s*\(", clean_text))
    calls: list[str] = []
    for match in matches:
        open_index = clean_text.find("(", match.start(), match.end())
        depth = 1
        index = open_index + 1
        string_delimiter = ""
        escaped = False
        while index < len(clean_text) and depth:
            char = clean_text[index]
            triple = clean_text[index : index + 3]
            if string_delimiter == '"""':
                if triple == '"""':
                    string_delimiter = ""
                    index += 3
                    continue
            elif string_delimiter:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == string_delimiter:
                    string_delimiter = ""
            elif triple == '"""':
                string_delimiter = '"""'
                index += 3
                continue
            elif char in {'"', "'"}:
                string_delimiter = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            index += 1
        if depth == 0:
            expression = re.sub(r"\s+", " ", clean_text[open_index + 1 : index - 1]).strip()
            calls.append(f"{function_name}({expression})")
    return list(dict.fromkeys(calls))


def extract_source_obligations(
    source_path: Path, source_row: dict[str, Any], route: dict[str, Any]
) -> list[str]:
    """Attach source-backed method, state, parameter and priority obligations."""
    obligations = list(route["obligations"])
    source_text = source_path.read_text(encoding="utf-8")
    commentless_text = strip_scala_comments(source_text)
    code_lines = [
        line.strip()
        for line in commentless_text.splitlines()
        if line.strip()
    ]

    if route["classification"] in HARDWARE_CATEGORIES:
        functions = sorted(set(DEFINITION_PATTERN.findall(commentless_text)))
        if functions:
            obligations.append(
                "Source functions whose behavior/parameters must be accounted for: "
                + ", ".join(functions)
                + "."
            )
        states = []
        for line in code_lines:
            for match in STATE_PATTERN.finditer(line):
                states.append(f"{match.group(1)} via {match.group(2)}")
        if states:
            obligations.append(
                "Observed storage/state declarations to preserve: "
                + "; ".join(dict.fromkeys(states))
                + "."
            )
        requirements = extract_guard_calls(source_text, "require")
        if requirements:
            obligations.append(
                "Exact source parameter/legal-range constraints: "
                + " | ".join(dict.fromkeys(requirements))
                + "."
            )
        assertions = extract_guard_calls(source_text, "assert")
        if assertions:
            obligations.append(
                "Exact source behavioral assertions/invariants: "
                + " | ".join(assertions)
                + "."
            )
        priority_lines = [
            line for line in code_lines if CONTROL_PATTERN.search(line)
        ]
        if priority_lines:
            obligations.append(
                "Observed priority/control branches (source order retained): "
                + " | ".join(dict.fromkeys(priority_lines))
                + "."
            )
        markers = source_row.get("hardware_markers", [])
        if markers:
            obligations.append(
                "Seed hardware markers are annotations only; source-level hardware "
                "ownership retains: " + ", ".join(markers) + "."
            )
        elif not states:
            obligations.append(
                "No lexical storage marker was required for inclusion; the routed "
                "algorithm/interface behavior remains in the planned family."
            )
    elif route["classification"] == "ELABORATION_CONFIG":
        configs = [
            item["name"]
            for item in source_row.get("declarations", [])
            if CONFIG_NAME.search(item["name"])
        ]
        if configs:
            obligations.append(
                "Configuration declarations to retain where consumed: "
                + ", ".join(configs)
                + "."
            )
    return obligations


def tracked_scala_files() -> list[str]:
    """Return all tracked Scala files under the three exact source roots."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", *SCOPE_ROOTS],
        cwd=AUXILIARY_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    paths = [
        item.decode("utf-8")
        for item in result.stdout.split(b"\0")
        if item and item.endswith(b".scala")
    ]
    return sorted(paths)


def current_auxiliary_commit() -> str:
    """Read the auxiliary repository commit used as the scan environment."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=AUXILIARY_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def load_and_check_seed() -> tuple[dict[str, Any], dict[str, dict[str, Any]], str]:
    """Bind the generation to the newest seed and recheck exact files and hashes."""
    seed_bytes = SEED_PATH.read_bytes()
    seed = json.loads(seed_bytes.decode("utf-8"))
    seed_hash = hashlib.sha256(seed_bytes).hexdigest()
    seed_rows = {
        row["path"]: row
        for row in seed["files"]
        if any(row["path"].startswith(root + "/") for root in SCOPE_ROOTS)
    }
    actual_paths = tracked_scala_files()
    if set(actual_paths) != set(seed_rows):
        missing = sorted(set(actual_paths) - set(seed_rows))
        stale = sorted(set(seed_rows) - set(actual_paths))
        raise RuntimeError(
            "Tracked Scala path set differs from latest seed; "
            f"missing_from_seed={missing[:12]}, stale_seed_paths={stale[:12]}"
        )

    counts = Counter(path.split("/", 2)[:2][0] + "/" + path.split("/", 2)[1] for path in actual_paths)
    normalized_counts = {
        root: sum(path.startswith(root + "/") for path in actual_paths)
        for root in SCOPE_ROOTS
    }
    if normalized_counts != EXPECTED_ROOT_COUNTS:
        raise RuntimeError(
            f"Owned source counts changed: {normalized_counts!r}; "
            f"expected {EXPECTED_ROOT_COUNTS!r}"
        )

    for path in actual_paths:
        actual_hash = hashlib.sha256((AUXILIARY_ROOT / path).read_bytes()).hexdigest()
        seed_hash_for_path = seed_rows[path].get("sha256")
        if actual_hash != seed_hash_for_path:
            raise RuntimeError(
                f"Source hash differs from current seed: {path} "
                f"seed={seed_hash_for_path} actual={actual_hash}"
            )
    if seed["source_file_count"] != 1736:
        raise RuntimeError(
            f"Seed source file count changed unexpectedly: {seed['source_file_count']}"
        )
    return seed, seed_rows, seed_hash


def make_scan(
    seed: dict[str, Any],
    seed_rows: dict[str, dict[str, Any]],
    seed_hash: str,
) -> dict[str, Any]:
    """Build the planning-only JSON fragment and target-level source index."""
    file_rows: list[dict[str, Any]] = []
    source_lists: dict[str, list[str]] = defaultdict(list)
    symbol_lists: dict[str, set[str]] = defaultdict(set)
    classification_counts: Counter[str] = Counter()
    declaration_count = 0
    locked_module_count = 0

    for path in sorted(seed_rows):
        source_row = seed_rows[path]
        route = classify_source(path, source_row)
        targets = [TARGETS[key]["path"] for key in route["target_ids"]]
        declarations = []
        for declaration in source_row.get("declarations", []):
            target = targets[0] if targets else None
            if target is None:
                disposition = route["declaration_disposition"]
            elif route["classification"] in HARDWARE_CATEGORIES:
                disposition = "PRIMARY_OWNER"
            else:
                disposition = "PRIMARY_OWNER_CONFIGURATION_INPUT"
            declarations.append(
                {
                    "name": declaration["name"],
                    "kind": declaration["kind"],
                    "python_target": target,
                    "disposition": disposition,
                }
            )
        declaration_count += len(declarations)
        locked_modules = list(source_row.get("locked_modules", []))
        locked_module_count += len(locked_modules)
        classification_counts[route["classification"]] += 1
        for target_id in route["target_ids"]:
            source_lists[target_id].append(path)
            symbol_lists[target_id].update(source_row.get("hardware_markers", []))

        feature_obligations = extract_source_obligations(
            AUXILIARY_ROOT / path,
            source_row,
            route,
        )
        file_rows.append(
            {
                "path": path,
                "source_sha256": source_row["sha256"],
                "classification": route["classification"],
                "reason": route["reason"],
                "python_targets": targets,
                "declaration_owners": declarations,
                "feature_obligations": feature_obligations,
                "scope_claim": SCOPE_CLAIM,
                "hardware_markers": list(source_row.get("hardware_markers", [])),
                "locked_modules": locked_modules,
            }
        )

    python_files = []
    for target_id in sorted(source_lists):
        target = TARGETS[target_id]
        target_file = AUXILIARY_ROOT / target["path"]
        dependencies = [
            TARGETS[key]["path"]
            for key in target["dependencies"]
            if key in source_lists
        ]
        python_files.append(
            {
                "path": target["path"],
                "existing": target_file.is_file(),
                "responsibility": target["responsibility"],
                "sources": sorted(source_lists[target_id]),
                "hardware_symbols": sorted(symbol_lists[target_id]),
                "required_configuration_modes": target["required_configuration_modes"],
                "needed_companion_dependencies": dependencies,
            }
        )

    actual_roots = {
        root: sum(row["path"].startswith(root + "/") for row in file_rows)
        for root in SCOPE_ROOTS
    }
    locked_source_file_count = sum(bool(row["locked_modules"]) for row in file_rows)
    if len(file_rows) != sum(EXPECTED_ROOT_COUNTS.values()):
        raise RuntimeError(f"Generated file count is wrong: {len(file_rows)}")
    if any(row["scope_claim"] != SCOPE_CLAIM for row in file_rows):
        raise RuntimeError("A file row has no planning-only scope claim")
    if any(
        owner["disposition"] == "PRIMARY_OWNER" and owner["python_target"] is None
        for row in file_rows
        for owner in row["declaration_owners"]
    ):
        raise RuntimeError("A primary symbol owner has no Build target")
    for row in file_rows:
        if row["locked_modules"] and (
            row["classification"] not in HARDWARE_CATEGORIES
            or not row["python_targets"]
        ):
            raise RuntimeError(
                "A locked module annotation has no hardware/mixed source owner candidate: "
                f"{row['path']}"
            )

    existing_count = sum(item["existing"] for item in python_files)
    new_count = len(python_files) - existing_count
    source_manifest = "\n".join(
        f"{row['path']}\0{row['source_sha256']}" for row in file_rows
    ).encode("utf-8")
    seed_policy = [
        "All tracked Scala files beneath upstream/rocket-chip, upstream/chisel3, and upstream/macros are included; the hidden .github CI example is tracked and classified TEST_ONLY.",
        "The current seed path set and every source SHA-256 are rechecked against git ls-files before generation.",
        "hardware_markers and locked_modules are copied as review annotations only; neither absence nor presence changes classification or grants implementation credit.",
        "Chisel compiler, FIRRTL/CIRCT emitter, plugin, macro, binder, and simulator code is HOST_TOOL or DECLARATION_SUPPORT; Amaranth supplies language/elaboration semantics and the Scala compiler is not rewritten as RTL.",
        "Chisel Queue/Decoupled, Arbiter, Counter, CDC, LFSR/PRNG, memory and coding helpers are explicitly routed to executable hardware families, including variants not selected by the locked CPU instance.",
        "CDE and Rocket host parameter graphs become explicit standard-library configuration inputs; the Scala configuration library is not copied one class at a time.",
        "AMBA AXI4/AXIS/AHB/APB and TileLink hardware plus every declared protocol mode remain assigned even if the locked top does not instantiate them.",
        "TEST_ONLY is used only for source tests, executable examples/cookbooks, CI samples, ground-test harnesses, or simulation-only memories; each such row carries a concrete source-tree reason.",
        "This is source ownership planning only. No Build implementation, syntax/import/export gate, behavior test, formal run, acceptance state, commit, or push is claimed.",
    ]
    return {
        "kind": "V2_ALL_SOURCE_INFRASTRUCTURE_SCAN",
        "phase": "PLANNING_ONLY_NO_IMPLEMENTATION_OR_VERIFICATION",
        "source_commit": seed["source_commit"],
        "seed_auxiliary_commit": seed.get("auxiliary_commit"),
        "scan_auxiliary_commit": current_auxiliary_commit(),
        "scan_seed_path": "validation/v2-all-source-scan-seed.json",
        "scan_seed_sha256": seed_hash,
        "source_file_manifest_sha256": hashlib.sha256(source_manifest).hexdigest(),
        "scope": "All tracked Scala source files owned by this infrastructure slice.",
        "scope_roots": list(SCOPE_ROOTS),
        "source_file_count": len(file_rows),
        "seed_source_file_count": seed["source_file_count"],
        "by_root": actual_roots,
        "declared_symbol_count": declaration_count,
        "seed_declared_symbol_count": seed["declared_symbol_count"],
        "seed_locked_source_file_count": seed["locked_source_file_count"],
        "locked_source_file_count": locked_source_file_count,
        "locked_module_count": locked_module_count,
        "locked_module_annotations": locked_module_count,
        "classification_counts": dict(sorted(classification_counts.items())),
        "coverage_complete": True,
        "acceptance_eligible": False,
        "implementation_or_verification_performed": False,
        "existing_reuse_build_count": existing_count,
        "new_aggregate_build_count": new_count,
        "new_build_aggregation_rule": (
            "New targets represent real cross-file behavior families with explicit "
            "parameter/state/protocol obligations; no one-Scala-one-Python mapping."
        ),
        "policy": seed_policy,
        "python_files": python_files,
        "files": file_rows,
    }


def write_scan(document: dict[str, Any]) -> None:
    """Write the owned generated JSON artifact in stable UTF-8/LF form."""
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(document, output, ensure_ascii=False, indent=2)
        output.write("\n")


def main() -> int:
    """Generate the source-mapped infrastructure scan fragment."""
    seed, seed_rows, seed_hash = load_and_check_seed()
    document = make_scan(seed, seed_rows, seed_hash)
    write_scan(document)
    print(
        json.dumps(
            {
                "output": str(OUTPUT_PATH),
                "source_file_count": document["source_file_count"],
                "by_root": document["by_root"],
                "classification_counts": document["classification_counts"],
                "existing_reuse_build_count": document["existing_reuse_build_count"],
                "new_aggregate_build_count": document["new_aggregate_build_count"],
                "seed_sha256": document["scan_seed_sha256"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
