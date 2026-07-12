# H5/H6 8x8 Factory-Egress Generalization Sweep

This fixed-circuit experiment tests whether the H7 zero-egress runtime penalty generalizes to lower-load H5/H6 circuits. Adjacent bans close factory `(3,3)` egress without moving logical qubits; equal-count remote bans control for lost usable cells.

## H5

| case | egress | bans | runtime | vs baseline | topology overhead | egress blocked | fail share | CNOT delta | nearest-factory delta | code distance | physical qubits | semantic match |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| h5_egress_2_baseline | 2 | 0 | 2,122,291 | +0.0000% | 26 | 1 | 0.000% | +0 | +0 | 15 | 27,000 | yes |
| h5_egress_1_ban_left | 1 | 1 | 2,122,291 | +0.0000% | 26 | 69 | 0.013% | +0 | +0 | 15 | 26,550 | yes |
| h5_egress_0_ban_both | 0 | 2 | 2,379,559 | +12.1222% | 257,294 | 485,190 | 49.048% | +0 | +0 | 15 | 26,100 | yes |
| h5_control_remote_ban_1 | 2 | 1 | 2,122,293 | +0.0001% | 28 | 3 | 0.001% | +0 | +0 | 15 | 26,550 | yes |
| h5_control_remote_ban_2 | 2 | 2 | 2,122,326 | +0.0016% | 61 | 2 | 0.000% | +0 | +0 | 15 | 26,100 | yes |

## H6

| case | egress | bans | runtime | vs baseline | topology overhead | egress blocked | fail share | CNOT delta | nearest-factory delta | code distance | physical qubits | semantic match |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| h6_egress_1_baseline | 1 | 0 | 4,576,291 | +0.0000% | 6 | 5 | 0.000% | +0 | +0 | 15 | 27,000 | yes |
| h6_egress_0_ban_down | 0 | 1 | 5,127,303 | +12.0406% | 551,018 | 1,010,479 | 47.802% | +0 | +0 | 15 | 26,550 | yes |
| h6_control_remote_ban_1 | 1 | 1 | 4,576,299 | +0.0002% | 14 | 4 | 0.000% | +0 | +0 | 15 | 26,550 | yes |
| h6_egress_2_move_q0 | 2 | 0 | 4,576,286 | -0.0001% | 1 | 5 | 0.000% | -3,652 | +1 | 15 | 27,000 | yes |

## Controlled contrasts

- H5 one-ban adjacent minus remote runtime: -2 beats (-0.0001 percentage points vs baseline).
- H5 two-ban adjacent minus remote runtime: +257,233 beats (+12.1205 percentage points vs baseline).
- H6 one-ban adjacent minus remote runtime: +551,004 beats (+12.0404 percentage points vs baseline).
- H6 opening a second egress changes runtime by -5 beats (-0.0001%). This case moves only q0 and is therefore a directional check, not as clean as the ban contrasts.
- H7 reference: zero to one egress reduced runtime by about 10.007%, while one to two egress produced no further improvement.
- Circuit-semantic fields must match within each molecule; code-distance changes, if any, remain part of final resource output but not the fixed-circuit runtime intervention.

## Execution resources

- peak qret RSS: 1,747,092 KiB (1.67 GiB)
- maximum GNU-time swaps: 0
- execution: sequential tmux session with `MemoryHigh=44G`, `MemoryMax=48G`
- diagnostic `libqret-core.so` SHA-256: `f833e2b5dc5f8449ea8522d71699e209c6c3c94638333c6d930f4d6475eefd90`
- local diagnostic patch SHA-256: `65180e945107e8f68eda3fea8561655a1f9dc5e0ff3f349065d1c0585bcf722c`
