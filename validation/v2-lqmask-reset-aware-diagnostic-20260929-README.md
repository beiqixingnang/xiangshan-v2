# LqMaskModule reset-aware bounded diagnostic

The full 100-bit input surface and all 64 public output bits were compared against the locked `LqMaskModule` closure for three cycles. The environment forced reset high on cycle 1 and low on cycles 2 and 3; all other inputs remained unconstrained. Yosys SAT returned success with 159,323 variables and 425,524 clauses.

Both target-side and reference-side output mutations produced counterexamples, so the two negative controls are decisive for this bounded miter. This is still a reset-constrained bounded result; it does not replace the existing `equiv_induct -undef` strict rail and does not increase `39/118`. The other three LoadQueueData members and the parent closure remain pending.
