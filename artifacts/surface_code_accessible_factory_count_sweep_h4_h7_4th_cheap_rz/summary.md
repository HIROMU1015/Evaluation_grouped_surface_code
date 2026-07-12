# H4-H7 Accessible Factory-Count Sweep (`rotation_precision=0.01`)

The compiled circuit, 10x10 logical mapping, four-cell central factory budget, magic period/stock, and QEC inputs are fixed. Inactive factory coordinates are banned so active factories plus banned cells always occupy four cells. Every active factory has two initial free egress cells.

## H4

| factories | min egress | runtime | vs four | marginal reduction | supply-floor residual | topology overhead | no stock | egress blocked | available factories mean | magic mean path | code distance | physical qubits | QV vs four | workload match |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 2 | 182,013 | +24.3173% | reference | +6,270 | 3 | 67,034 | 158 | 0.151 | 3.048 | 13 | 32,448 | +17.8283% | yes |
| 2 | 2 | 151,372 | +3.3891% | +16.8345% | +63,501 | 1 | 8,269 | 0 | 1.140 | 2.455 | 13 | 32,448 | +2.5493% | yes |
| 3 | 2 | 148,057 | +1.1249% | +2.1900% | +89,476 | 1 | 3,982 | 0 | 2.155 | 2.005 | 13 | 32,448 | +0.8147% | yes |
| 4 | 2 | 146,410 | +0.0000% | +1.1124% | +102,474 | 1 | 1,333 | 0 | 3.448 | 1.858 | 13 | 32,448 | +0.0000% | yes |

## H5

| factories | min egress | runtime | vs four | marginal reduction | supply-floor residual | topology overhead | no stock | egress blocked | available factories mean | magic mean path | code distance | physical qubits | QV vs four | workload match |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 2 | 384,263 | +6.0586% | reference | +100,180 | 13 | 51,939 | 311 | 0.270 | 3.314 | 13 | 32,448 | +4.5167% | yes |
| 2 | 2 | 369,614 | +2.0154% | +3.8122% | +227,578 | 1 | 10,959 | 0 | 1.235 | 2.829 | 13 | 32,448 | +1.5908% | yes |
| 3 | 2 | 364,739 | +0.6699% | +1.3189% | +270,048 | 1 | 5,014 | 0 | 2.291 | 2.337 | 13 | 32,448 | +0.5053% | yes |
| 4 | 2 | 362,312 | +0.0000% | +0.6654% | +291,293 | 1 | 1,235 | 0 | 3.621 | 2.196 | 13 | 32,448 | +0.0000% | yes |

## H6

| factories | min egress | runtime | vs four | marginal reduction | supply-floor residual | topology overhead | no stock | egress blocked | available factories mean | magic mean path | code distance | physical qubits | QV vs four | workload match |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 2 | 746,141 | +4.6634% | reference | +486,188 | 3 | 69,899 | 73 | 0.200 | 3.475 | 15 | 43,200 | +3.3452% | yes |
| 2 | 2 | 723,822 | +1.5326% | +2.9913% | +593,846 | 1 | 15,835 | 2 | 1.001 | 3.107 | 15 | 43,200 | +1.1363% | yes |
| 3 | 2 | 716,387 | +0.4897% | +1.0272% | +629,736 | 1 | 6,790 | 0 | 2.033 | 2.668 | 15 | 43,200 | +0.3599% | yes |
| 4 | 2 | 712,896 | +0.0000% | +0.4873% | +648,084 | -176 | 1,328 | 0 | 3.548 | 2.484 | 15 | 43,200 | +0.0000% | yes |

## H7

| factories | min egress | runtime | vs four | marginal reduction | supply-floor residual | topology overhead | no stock | egress blocked | available factories mean | magic mean path | code distance | physical qubits | QV vs four | workload match |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 2 | 1,430,306 | +3.2058% | reference | +1,083,108 | 848 | 110,690 | 511 | 0.176 | 4.048 | 15 | 43,200 | +2.3977% | yes |
| 2 | 2 | 1,400,281 | +1.0393% | +2.0992% | +1,226,256 | 850 | 19,607 | 6 | 1.038 | 3.206 | 15 | 43,200 | +0.7838% | yes |
| 3 | 2 | 1,390,279 | +0.3176% | +0.7143% | +1,273,976 | 853 | 7,966 | 0 | 2.108 | 2.968 | 15 | 43,200 | +0.2525% | yes |
| 4 | 2 | 1,385,877 | +0.0000% | +0.3166% | +1,298,605 | 684 | 1,229 | 0 | 3.665 | 2.626 | 15 | 43,200 | +0.0000% | yes |

## Validity and execution

- Fixed logical workload match: all cases. QASM/optimized IR, logical gates/depth, and magic demand/depth are unchanged.
- Expected architecture differences are `ALLOCATE_MAGIC_FACTORY` count and `runtime_without_topology`, because qret includes factory supply in that runtime estimate.
- Active factories plus banned cells remain four and usable non-factory cells remain 96 in every case.
- Physical-qubit count is constant within each molecule.
- Factory egress rejection should remain negligible; a large value indicates that factory count is confounded by access geometry.
- peak qret RSS: 962,052 KiB (0.92 GiB)
- maximum GNU-time swaps: 0
- intended execution: sequential tmux session with `MemoryHigh=44G`, `MemoryMax=48G`
- diagnostic `libqret-core.so` SHA-256: `f833e2b5dc5f8449ea8522d71699e209c6c3c94638333c6d930f4d6475eefd90`
- local diagnostic patch SHA-256: `65180e945107e8f68eda3fea8561655a1f9dc5e0ff3f349065d1c0585bcf722c`

## Interpretation

- Rows matching the pure supply floor `ceil(magic_count * 15 / factory_count)` within 0.1% (minimum tolerance 100 beats): none.
- Minimum tested factory count within 1% of the four-factory runtime: H4:N=4, H5:N=3, H6:N=3, H7:N=3.
- A large positive supply-floor residual means the remaining circuit/dependency schedule, rather than factory generation throughput, sets runtime.
- Egress-blocked and no-stock counts are reported separately so supply capacity is not confused with the zero-egress pathology.
