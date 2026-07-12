# H4-H7 Accessible Factory-Count Sweep

The compiled circuit, 10x10 logical mapping, four-cell central factory budget, magic period/stock, and QEC inputs are fixed. Inactive factory coordinates are banned so active factories plus banned cells always occupy four cells. Every active factory has two initial free egress cells.

## H4

| factories | min egress | runtime | vs four | marginal reduction | supply-floor residual | topology overhead | no stock | egress blocked | available factories mean | magic mean path | code distance | physical qubits | QV vs four | workload match |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 2 | 2,769,017 | +240.1390% | reference | +16 | 1 | 3,658,734 | 136 | 0.048 | 2.539 | 15 | 43,200 | +205.0581% | yes |
| 2 | 2 | 1,384,520 | +70.0709% | +49.9996% | +19 | 1 | 759,441 | 53 | 0.295 | 3.258 | 15 | 43,200 | +62.4146% | yes |
| 3 | 2 | 923,027 | +13.3823% | +33.3323% | +26 | 1 | 220,857 | 52 | 0.933 | 2.729 | 13 | 32,448 | +13.2237% | yes |
| 4 | 2 | 814,084 | +0.0000% | +11.8028% | +121,833 | 1 | 12,970 | 0 | 3.395 | 1.846 | 13 | 32,448 | +0.0000% | yes |

## H5

| factories | min egress | runtime | vs four | marginal reduction | supply-floor residual | topology overhead | no stock | egress blocked | available factories mean | magic mean path | code distance | physical qubits | QV vs four | workload match |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 2 | 7,138,609 | +236.3633% | reference | +18 | 1 | 8,715,841 | 162 | 0.052 | 2.836 | 15 | 43,200 | +205.8094% | yes |
| 2 | 2 | 3,569,317 | +68.1823% | +49.9998% | +21 | 1 | 1,835,823 | 167 | 0.309 | 3.541 | 15 | 43,200 | +61.4690% | yes |
| 3 | 2 | 2,379,559 | +12.1222% | +33.3329% | +28 | 1 | 485,555 | 119 | 1.012 | 3.115 | 15 | 43,200 | +12.1879% | yes |
| 4 | 2 | 2,122,291 | +0.0000% | +10.8116% | +337,617 | 26 | 20,200 | 1 | 3.533 | 2.152 | 15 | 43,200 | +0.0000% | yes |

## H6

| factories | min egress | runtime | vs four | marginal reduction | supply-floor residual | topology overhead | no stock | egress blocked | available factories mean | magic mean path | code distance | physical qubits | QV vs four | workload match |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 2 | 15,382,217 | +236.1285% | reference | +16 | 1 | 19,639,909 | 1,003 | 0.050 | 2.931 | 17 | 55,488 | +208.0304% | yes |
| 2 | 2 | 7,691,122 | +68.0646% | +49.9999% | +21 | 1 | 3,915,048 | 258 | 0.311 | 3.794 | 17 | 55,488 | +61.8494% | yes |
| 3 | 2 | 5,127,427 | +12.0433% | +33.3332% | +26 | 1 | 1,011,452 | 222 | 1.025 | 3.234 | 15 | 43,200 | +11.8417% | yes |
| 4 | 2 | 4,576,290 | +0.0000% | +10.7488% | +730,735 | 5 | 22,270 | 3 | 3.529 | 2.394 | 15 | 43,200 | +0.0000% | yes |

## H7

| factories | min egress | runtime | vs four | marginal reduction | supply-floor residual | topology overhead | no stock | egress blocked | available factories mean | magic mean path | code distance | physical qubits | QV vs four | workload match |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 2 | 29,575,609 | +233.3703% | reference | +18 | 1 | 36,995,890 | 1,327 | 0.051 | 3.569 | 17 | 55,488 | +209.9176% | yes |
| 2 | 2 | 14,787,817 | +66.6853% | +50.0000% | +21 | 1 | 7,428,117 | 239 | 0.315 | 3.802 | 17 | 55,488 | +61.5228% | yes |
| 3 | 2 | 9,858,559 | +11.1237% | +33.3332% | +28 | 1 | 1,851,625 | 714 | 1.051 | 3.441 | 17 | 55,488 | +11.4768% | yes |
| 4 | 2 | 8,871,700 | +0.0000% | +10.0102% | +1,476,964 | 838 | 39,040 | 0 | 3.713 | 2.265 | 17 | 55,488 | +0.0000% | yes |

## Validity and execution

- Fixed logical workload match: all cases. QASM/optimized IR, logical gates/depth, and magic demand/depth are unchanged.
- Expected architecture differences are `ALLOCATE_MAGIC_FACTORY` count and `runtime_without_topology`, because qret includes factory supply in that runtime estimate.
- Active factories plus banned cells remain four and usable non-factory cells remain 96 in every case.
- Physical-qubit count constant within each molecule: no; changes are caused by code-distance threshold crossings, not cell-budget changes.
- Factory egress rejection should remain negligible; a large value indicates that factory count is confounded by access geometry.
- peak qret RSS: 4,096,328 KiB (3.91 GiB)
- maximum GNU-time swaps: 0
- intended execution: sequential tmux session with `MemoryHigh=44G`, `MemoryMax=48G`
- diagnostic `libqret-core.so` SHA-256: `f833e2b5dc5f8449ea8522d71699e209c6c3c94638333c6d930f4d6475eefd90`
- local diagnostic patch SHA-256: `65180e945107e8f68eda3fea8561655a1f9dc5e0ff3f349065d1c0585bcf722c`

## Interpretation

- With one to three factories, `runtime_without_topology` agrees with `ceil(magic_count * 15 / factory_count)` within 28 beats across all molecules. These cases are directly magic-supply limited.
- With four factories, runtime exceeds that pure supply floor by 121,833-1,476,964 beats. The critical path has crossed to the remaining circuit/dependency schedule.
- The fourth factory still reduces runtime by about 10-12%, but four factories are the first tested count no longer governed by the pure inverse factory-count law.
- Egress-blocked counts stay negligible relative to no-stock counts, so the observed scaling is a supply-capacity effect rather than a recurrence of the zero-egress pathology.
