# DCache MetaArray reset-aware diagnostic

The L1FlagMetaArray public-output miter passes a three-cycle SAT check after forcing zero initial state and applying reset at the first timestep. The same setup passes all requested base cases but fails every induction step through length three. This supports a reset and unconstrained-initial-state investigation, not strict equivalence. The canonical strict evidence remains `STRICT_PENDING` with a zero count delta; locked references and the Build were not changed.
