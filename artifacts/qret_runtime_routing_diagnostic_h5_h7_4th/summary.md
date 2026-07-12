# Fixed-circuit qret routing diagnostic

The compiled circuit is fixed within each molecule. This experiment changes only the grid topology and records aggregate routing counters.

| case | runtime (beats) | vs H7 10x10 | blocked beat advances | max no-run streak | magic fail % | CNOT fail % | magic mean path | CNOT mean path | semantic match |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| h5_aware_8x8 | 2,122,291 | control | 2,122,290 | 12 | 52.634% | 68.681% | 2.281 | 5.117 | yes |
| h7_aware_8x8 | 9,858,370 | +11.122% | 9,858,369 | 12 | 66.860% | 70.001% | 5.258 | 5.674 | yes |
| h7_aware_8x10 | 8,871,631 | -0.001% | 8,871,630 | 12 | 52.488% | 70.241% | 2.052 | 5.255 | yes |
| h7_aware_10x10 | 8,871,700 | +0.000% | 8,871,699 | 12 | 52.482% | 70.283% | 2.265 | 5.086 | yes |

`failed_attempts` means `ScLsSimulator::Run` rejected an otherwise runnable queue candidate at that beat. It is an aggregate contention/scheduling signal, not a simulator-internal failure-reason classification.

## Findings

- H7 topology-free runtime is fixed at 8,870,862 beats. The 8x8 runtime penalty is 986,670 beats, exactly equal to the topology-overhead increase of 986,670 beats versus 10x10.
- H7 8x8 increases the mean magic path from 2.265 to 5.258 coordinates (+132.1%). Rejected magic attempts rise by +82.7%, and their fraction rises from 52.48% to 66.86%.
- H7 CNOT rejection does not increase: its rejected-attempt fraction is 70.00% on 8x8 and 70.28% on 10x10. Its mean path increases only +11.6%.
- H7 8x10 returns to the baseline runtime while its mean magic path is 2.052. This places the observed transition between 8x8 and the first tested grid with one expanded dimension.
- The maximum consecutive no-run streak remains 12 beats in every case. The penalty is therefore associated with repeated aggregate routing/scheduling rejection, not a longer single stall episode.

These observations upgrade the generic routing-congestion explanation: the H7 8x8 penalty is specifically associated with longer magic-delivery paths and many more rejected `LATTICE_SURGERY_MAGIC` attempts. Exact simulator failure reasons and simultaneous cell occupancy remain unresolved because this diagnostic records aggregate `Run` outcomes only.

## Execution resources

- peak qret RSS: 3,381,192 KiB (3.22 GiB)
- maximum swaps reported by GNU time: 0
- execution: sequential tmux session with `MemoryHigh=44G`, `MemoryMax=48G`
- diagnostic `libqret-core.so` SHA-256: `f88ef1f235a65c3bd8cbb0b2920c3b73e5617165fc538c442fa46e45313691d8`
- library hash capture: `post_run_rebuild_from_same_source_patch`
- local diagnostic patch SHA-256: `d9affe2692dcaf110db55e7fa4c480b62f7a045ca902a3755992d1291b7fbbdc`
