# Fixed-circuit qret routing diagnostic

The compiled circuit is fixed within each molecule. This experiment changes only the grid topology and records aggregate routing counters.

| case | runtime (beats) | vs H7 10x10 | blocked beat advances | max no-run streak | magic fail % | CNOT fail % | magic mean path | CNOT mean path | semantic match |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| h7_aware_8x8 | 9,858,370 | +11.122% | 9,858,369 | 12 | 66.860% | 70.001% | 5.258 | 5.674 | yes |
| h7_aware_8x10 | 8,871,631 | -0.001% | 8,871,630 | 12 | 52.488% | 70.241% | 2.052 | 5.255 | yes |
| h7_aware_10x10 | 8,871,700 | +0.000% | 8,871,699 | 12 | 52.482% | 70.283% | 2.265 | 5.086 | yes |

## Magic failure reasons

Percentages use failed `LATTICE_SURGERY_MAGIC` attempts as the denominator.

| case | qubit busy | no stock | factory egress | target access | disconnected | other/dependency | reason sum | stock min / mean | available factories mean |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| h7_aware_8x8 | 53.420% | 0.005% | 46.218% | 0.216% | 0.141% | 0.000% | yes | 0 / 9,794.6 | 2.043 |
| h7_aware_8x10 | 98.159% | 1.792% | 0.000% | 0.025% | 0.023% | 0.000% | yes | 0 / 24,567.2 | 3.828 |
| h7_aware_10x10 | 98.182% | 1.793% | 0.000% | 0.014% | 0.012% | 0.000% | yes | 0 / 19,016.5 | 3.713 |

## Factory access geometry

Free-neighbor counts use the initial topology occupancy and four-neighbor connectivity.

| case | initial free neighbors m0/m1/m2/m3 | successful use m0/m1/m2/m3 |
|---|---:|---:|
| h7_aware_8x8 | 0/1/2/2 | 82/657,223/657,182/657,219 |
| h7_aware_8x10 | 2/2/2/2 | 526,933/380,541/474,892/589,340 |
| h7_aware_10x10 | 2/2/2/2 | 590,364/591,445/328,050/461,847 |

`failed_attempts` means `ScLsSimulator::Run` rejected an otherwise runnable queue candidate. Version 2 classifies the top-level rejection branch but does not retain per-attempt event logs or a cell-occupancy trace.

## Findings

- H7 topology-free runtime is fixed at 8,870,862 beats. The 8x8 runtime penalty is 986,670 beats, exactly equal to the topology-overhead increase of 986,670 beats versus 10x10.
- H7 8x8 increases the mean magic path from 2.265 to 5.258 coordinates (+132.1%). Rejected magic attempts rise by +82.7%, and their fraction rises from 52.48% to 66.86%.
- H7 CNOT rejection does not increase: its rejected-attempt fraction is 70.00% on 8x8 and 70.28% on 10x10. Its mean path increases only +11.6%.
- H7 8x10 returns to the baseline runtime while its mean magic path is 2.052. This places the observed transition between 8x8 and the first tested grid with one expanded dimension.
- The maximum consecutive no-run streak remains 12 beats in every case. The penalty is therefore associated with repeated aggregate routing/scheduling rejection, not a longer single stall episode.
- The largest 8x8-versus-10x10 increase is `factory_egress_blocked`: +1,838,510 rejected attempts.
- Magic stock is not exhausted continuously: 8x8 stock min/mean is 0/9,794.6, versus 0/19,016.5 on 10x10.
- H7 8x8 factory m0 has 0 initially free neighbors and is used only 82 times; on 10x10 it has 2 free neighbors and 590,364 uses.
- The reason counts sum exactly to total failed magic attempts in every case.

The reason breakdown identifies which top-level magic scheduling or routing branch accounts for the 8x8 penalty. Simultaneous cell occupancy and the exact blocked cells remain unresolved.

## Execution resources

- peak qret RSS: 3,381,836 KiB (3.23 GiB)
- maximum swaps reported by GNU time: 0
- execution: sequential tmux session with `MemoryHigh=44G`, `MemoryMax=48G`
- diagnostic `libqret-core.so` SHA-256: `f833e2b5dc5f8449ea8522d71699e209c6c3c94638333c6d930f4d6475eefd90`
- library hash capture: `at_case_execution`
- local diagnostic patch SHA-256: `65180e945107e8f68eda3fea8561655a1f9dc5e0ff3f349065d1c0585bcf722c`
