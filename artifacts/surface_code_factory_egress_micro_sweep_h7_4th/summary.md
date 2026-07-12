# H7 8x8 Factory-Egress Causal Micro-Sweep

The logical circuit, grid, factory coordinate set, QEC settings, and magic supply settings are fixed. The intervention opens zero, one, or two initially free neighbors at physical factory coordinate `(3,3)`; the symbol-rotation case preserves geometry.

| case | egress | runtime | vs baseline | topology overhead | egress blocked | egress fail share | magic mean path | CNOT objective delta | nearest-factory delta | trapped-coordinate uses | semantic match |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| egress_0_baseline | 0 | 9,858,370 | +0.0000% | 987,508 | 1,838,510 | 46.218% | 5.258 | +0 | +0 | 82 | yes |
| egress_1_left | 1 | 8,871,838 | -10.0070% | 976 | 25 | 0.001% | 3.081 | +37,316 | +377,908 | 417,199 | yes |
| egress_1_down | 1 | 8,871,822 | -10.0072% | 960 | 56 | 0.003% | 3.045 | +32,264 | +275,220 | 378,690 | yes |
| egress_2_both | 2 | 8,872,721 | -9.9981% | 1,859 | 13 | 0.001% | 3.018 | +69,580 | +653,128 | 518,585 | yes |
| egress_0_symbol_rotate | 0 | 9,858,370 | +0.0000% | 987,508 | 1,838,510 | 46.218% | 5.258 | +0 | +0 | 82 | yes |

## Diagnostic checks

- Symbol-only control runtime change: +0.000000%.
- Lowest open-case runtime: `egress_1_down` at 8,871,822 beats (-10.0072%).
- Lowest open-case egress rejection: `egress_2_both` at 13 attempts.
- One free egress is sufficient in both directions: left/down reduce egress rejection from 1,838,510 to 25/56, and runtime by 10.0070%/10.0072%.
- Two free egress cells reduce rejection to 13 but do not improve runtime beyond the one-egress cases; the response is threshold-like rather than monotonic.
- Symbol rotation is bit-identical for runtime and rejection. The blocked physical coordinate remains at 82 successful uses, so the effect follows geometry rather than factory ID.
- Opening egress worsens, rather than improves, both static distance objectives; a runtime reduction therefore cannot be attributed to shorter static distances.
- Detailed reason counts sum to total failed magic attempts and circuit-semantic fields match the baseline in every case.

## Execution resources

- peak qret RSS: 3,381,536 KiB (3.22 GiB)
- maximum GNU-time swaps: 0
- intended execution: sequential tmux session with `MemoryHigh=44G`, `MemoryMax=48G`
- diagnostic `libqret-core.so` SHA-256: `f833e2b5dc5f8449ea8522d71699e209c6c3c94638333c6d930f4d6475eefd90`
- local diagnostic patch SHA-256: `65180e945107e8f68eda3fea8561655a1f9dc5e0ff3f349065d1c0585bcf722c`
