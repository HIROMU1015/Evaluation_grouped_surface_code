# H4-H6 Paired-Precision Dim2 Factory-Saturation Sweep

Each molecule/precision uses one fixed optimized IR. Active factory count changes from 4 to 6 to 8 inside one fixed eight-cell central factory/ban budget on a 10x10 Dim2 plane. Absolute runtime is not compared across precision as an architecture effect.

## rotation_precision=1e-05

| molecule | factories | runtime | vs four | vs eight | marginal reduction | runtime no topology | supply-floor residual | topology overhead | nearest-factory mean | min egress | cells | code distance | QV vs four | workload match |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| H4 | 4 | 814,085 | +0.0000% | +0.0971% | reference | 814,083 | +121,833 | +2 | 2.778 | 1 | 92 | 13 | +0.0000% | yes |
| H4 | 6 | 813,544 | -0.0665% | +0.0306% | +0.0665% | 813,564 | +352,064 | -20 | 2.444 | 1 | 92 | 13 | -5.1342% | yes |
| H4 | 8 | 813,295 | -0.0970% | +0.0000% | +0.0306% | 813,360 | +467,235 | -65 | 2.000 | 1 | 92 | 13 | -5.6195% | yes |
| H5 | 4 | 2,122,293 | +0.0000% | +0.0410% | reference | 2,122,265 | +337,617 | +28 | 3.182 | 1 | 92 | 15 | +0.0000% | yes |
| H5 | 6 | 2,121,700 | -0.0279% | +0.0130% | +0.0279% | 2,121,616 | +931,851 | +84 | 2.818 | 1 | 92 | 15 | -3.0711% | yes |
| H5 | 8 | 2,121,424 | -0.0409% | +0.0000% | +0.0130% | 2,121,319 | +1,228,995 | +105 | 2.364 | 1 | 92 | 15 | -3.4865% | yes |
| H6 | 4 | 4,578,626 | +0.0000% | +0.0753% | reference | 4,576,285 | +730,735 | +2,341 | 3.308 | 1 | 92 | 15 | +0.0000% | yes |
| H6 | 6 | 4,575,461 | -0.0691% | +0.0061% | +0.0691% | 4,575,488 | +2,011,788 | -27 | 2.923 | 1 | 92 | 15 | -3.8249% | yes |
| H6 | 8 | 4,575,183 | -0.0752% | +0.0000% | +0.0061% | 4,575,149 | +2,652,374 | +34 | 2.538 | 1 | 92 | 15 | -4.3135% | yes |

## rotation_precision=1e-02

| molecule | factories | runtime | vs four | vs eight | marginal reduction | runtime no topology | supply-floor residual | topology overhead | nearest-factory mean | min egress | cells | code distance | QV vs four | workload match |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| H4 | 4 | 146,416 | +0.0000% | +0.4521% | reference | 146,409 | +102,474 | +7 | 2.778 | 1 | 92 | 13 | +0.0000% | yes |
| H4 | 6 | 145,757 | -0.4501% | +0.0000% | +0.4501% | 146,022 | +116,732 | -265 | 2.444 | 1 | 92 | 13 | -0.8089% | yes |
| H4 | 8 | 145,757 | -0.4501% | +0.0000% | +0.0000% | 145,951 | +123,983 | -194 | 2.000 | 1 | 92 | 13 | -1.0699% | yes |
| H5 | 4 | 362,312 | +0.0000% | +0.1700% | reference | 362,311 | +291,293 | +1 | 3.182 | 1 | 92 | 13 | +0.0000% | yes |
| H5 | 6 | 361,697 | -0.1697% | +0.0000% | +0.1697% | 361,948 | +314,603 | -251 | 2.818 | 1 | 92 | 13 | -0.4740% | yes |
| H5 | 8 | 361,697 | -0.1697% | +0.0000% | +0.0000% | 361,891 | +326,382 | -194 | 2.364 | 1 | 92 | 13 | -0.6227% | yes |
| H6 | 4 | 715,440 | +0.0000% | +0.4363% | reference | 713,072 | +648,084 | +2,368 | 3.308 | 1 | 92 | 15 | +0.0000% | yes |
| H6 | 6 | 712,332 | -0.4344% | +0.0000% | +0.4344% | 712,705 | +669,380 | -373 | 2.923 | 1 | 92 | 15 | -0.4687% | yes |
| H6 | 8 | 712,332 | -0.4344% | +0.0000% | +0.0000% | 712,560 | +680,066 | -228 | 2.538 | 1 | 92 | 15 | -0.5154% | yes |

## Four-to-Eight Factory Runtime Reduction

| molecule | reduction at 1e-5 | reduction at 1e-2 | six-to-eight residual at 1e-5 | six-to-eight residual at 1e-2 |
|---|---:|---:|---:|---:|
| H4 | +0.0970% | +0.4501% | +0.0306% | +0.0000% |
| H5 | +0.0409% | +0.1697% | +0.0130% | +0.0000% |
| H6 | +0.0752% | +0.4344% | +0.0061% | +0.0000% |

## Validity and Execution

- QASM and optimized-IR hashes are fixed within each molecule/precision.
- Non-factory gate counts/depths and magic/feedback demand must remain fixed. Only factory-allocation count and architecture-dependent runtime/resource fields may change.
- Active factories plus banned cells remain eight, leaving 92 non-factory cells in every case.
- Factory sets are nested and symbols 0-3 retain their coordinates. Additional sources change both aggregate supply throughput and nearest-source availability within the fixed budget.
- Code-distance changes, if present, affect physical qubits/QV but not the primary beat-runtime conclusion.
- peak qret RSS: 1,741,516 KiB (1.66 GiB)
- maximum GNU-time swaps: 0
- H7 follow-up trigger (> 1.0% unresolved runtime effect): no
- qret executable SHA-256: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- qret core library SHA-256: `9e39f84863d499ac71bd76c86cf88cb44d5d2e9416fb580bf6aba3aa9c49feb6`
