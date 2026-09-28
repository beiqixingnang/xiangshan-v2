# FrontendBridge `instr_uncache_a` static diagnostic

This report records a source-backed diagnosis of the first public queue partition for `Build-Cpu.Memory.FrontendBridge`. It is diagnostic evidence only; it does not change the strict numerator or claim a formal result.

The existing partition result is `STRICT_PENDING`: Yosys created 54 output obligations for `instr_uncache_a`, with `proven_cells=0` and `unproven_cells=54`. This diagnostic did not run WSL formal. The stored result remains at [v2-frontendbridge-public-queue-strict-results.json](v2-frontendbridge-public-queue-strict-results.json).

The locked `InstrUncacheBuffer` A edge is two `Queue(2, pipe=false, flow=false)` stages. `Queue2_TLBundleA_26` uses one-bit enqueue/dequeue pointers, `maybe_full`, and a two-entry `ram_2x132`; `InstrUncacheBuffer.sv` supplies opcode `4`, size `3`, source `0`, mask `8'hFF`, data `0`, and corrupt `0`, while the public partition observes only `param`, `address`, `corrupt`, `out_a_valid`, and `in_a_ready`. The Build's `BufferedEdge((3, 48, 1), "instr_uncache_a")` has the same two-stage handshake and the same observed constants.

The valid transfer behavior is aligned. A deterministic two-stage serial queue model was checked from reset for all input/ready choices through depth 12; whenever `deq_valid` is high, target and locked Queue(2) emit the same FIFO payload and handshake result.

The public bit-level view still has a concrete reachable mismatch in an invalid cycle. After one request is accepted, propagated through both stages, and then consumed, the locked queue advances `deq_ptr` and reads the other RAM slot. The target count queue keeps exposing `data0`. Therefore, once `out_a_valid` falls, `out_a_bits_address` (and the other selected payload bits) can differ even though Decoupled semantics make those bits don't-care. This is a proof-contract mismatch caused by unconditional comparison of payload bits, rather than a valid transaction mismatch.

There is a second independent proof obstacle. The locked reference view removes `ENABLE_INITIAL_MEM_` and `ENABLE_INITIAL_REG_`; its queue RAM contents are unconstrained before writes. Amaranth `Signal` storage in the target has deterministic zero initialization in the exported RTL. Unconditional comparison therefore also asks Yosys to equate invalid-cycle payloads across incompatible initial-memory contracts. The target's two-bit count additionally admits unreachable state `3` under `equiv_induct -undef`, while the reference pointer/full encoding has no equivalent occupancy state.

The minimal repair belongs first in the proof contract: gate the payload comparison by the corresponding `valid` output (or compare only the valid/ready lanes for this partition), and state the invalid payload policy explicitly. If exact invalid-cycle bit behavior is required, a larger pure-Amaranth queue rewrite must retain enqueue/dequeue pointers and expose `storage[deq_ptr]`; that still needs an explicit initialization policy or a valid-gated proof because the locked RAM is intentionally uninitialized. No Build or direct-test edit is justified by this diagnostic, and no strict count is added.

Machine-readable details are in [the companion JSON](v2-build-cpu-memory-frontendbridge-public-queue-instr-uncache-a-diagnostic-20260928T191437Z.json).
