# H4/H7 Paired-Precision DistributedDim2 Communication Sweep

Each molecule/precision uses one fixed optimized IR. Two balanced explicit partitions and entanglement-generation periods 1/15/100 are compared on the same two 10x10 planes, four magic factories, one entanglement link, and fixed stock limits. Absolute runtime is not compared across precision as an architecture effect.

## rotation_precision=1e-05

| molecule | partition | period | runtime | vs period=1 | topology overhead | static cut | ent count | ent depth | count estimate | runtime-estimate | code distance | QV vs period=1 | workload match |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| H4 | low_cut | 1 | 1,099,280 | +0.0000% | 406,905 | 7,480 | 7,480 | 6,185 | 7,480 | +1,091,800 | 15 | +0.0000% | yes |
| H4 | low_cut | 15 | 1,099,280 | +0.0000% | 406,905 | 7,480 | 7,480 | 6,185 | 112,200 | +987,080 | 15 | +0.0000% | yes |
| H4 | low_cut | 100 | 1,099,280 | +0.0000% | 349,454 | 7,480 | 7,480 | 6,185 | 748,000 | +351,280 | 15 | +0.0000% | yes |
| H4 | high_cut | 1 | 1,274,802 | +0.0000% | 582,485 | 10,252 | 10,252 | 7,455 | 10,252 | +1,264,550 | 15 | +0.0000% | yes |
| H4 | high_cut | 15 | 1,274,802 | +0.0000% | 582,485 | 10,252 | 10,252 | 7,455 | 153,780 | +1,121,022 | 15 | +0.0000% | yes |
| H4 | high_cut | 100 | 1,274,802 | +0.0000% | 249,094 | 10,252 | 10,252 | 7,455 | 1,025,200 | +249,602 | 15 | +0.0000% | yes |
| H7 | low_cut | 1 | 11,654,617 | +0.0000% | 3,716,820 | 94,848 | 94,848 | 79,801 | 94,848 | +11,559,769 | 17 | +0.0000% | yes |
| H7 | low_cut | 15 | 11,654,617 | +0.0000% | 3,716,820 | 94,848 | 94,848 | 79,801 | 1,422,720 | +10,231,897 | 17 | +0.0000% | yes |
| H7 | low_cut | 100 | 11,654,617 | +0.0000% | 2,160,922 | 94,848 | 94,848 | 79,801 | 9,484,800 | +2,169,817 | 17 | +0.0000% | yes |
| H7 | high_cut | 1 | 12,517,577 | +0.0000% | 5,123,626 | 139,280 | 139,280 | 101,282 | 139,280 | +12,378,297 | 17 | +0.0000% | yes |
| H7 | high_cut | 15 | 12,517,577 | +0.0000% | 5,123,626 | 139,280 | 139,280 | 101,282 | 2,089,200 | +10,428,377 | 17 | +0.0000% | yes |
| H7 | high_cut | 100 | 13,942,639 | +11.3845% | 14,186 | 139,280 | 139,280 | 101,282 | 13,928,000 | +14,639 | 17 | +9.7370% | yes |

## rotation_precision=1e-02

| molecule | partition | period | runtime | vs period=1 | topology overhead | static cut | ent count | ent depth | count estimate | runtime-estimate | code distance | QV vs period=1 | workload match |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| H4 | low_cut | 1 | 139,072 | +0.0000% | 37,289 | 7,480 | 7,480 | 6,185 | 7,480 | +131,592 | 13 | +0.0000% | yes |
| H4 | low_cut | 15 | 139,072 | +0.0000% | 25,527 | 7,480 | 7,480 | 6,185 | 112,200 | +26,872 | 13 | +0.0000% | yes |
| H4 | low_cut | 100 | 748,224 | +438.0120% | 38 | 7,480 | 7,480 | 6,185 | 748,000 | +224 | 13 | +310.3347% | yes |
| H4 | high_cut | 1 | 137,899 | +0.0000% | 39,076 | 10,252 | 10,252 | 7,455 | 10,252 | +127,647 | 13 | +0.0000% | yes |
| H4 | high_cut | 15 | 156,796 | +13.7035% | 2,656 | 10,252 | 10,252 | 7,455 | 153,780 | +3,016 | 13 | +9.5287% | yes |
| H4 | high_cut | 100 | 1,025,301 | +643.5159% | 1 | 10,252 | 10,252 | 7,455 | 1,025,200 | +101 | 13 | +447.5769% | yes |
| H7 | low_cut | 1 | 1,286,026 | +0.0000% | 269,612 | 94,848 | 94,848 | 79,801 | 94,848 | +1,191,178 | 15 | +0.0000% | yes |
| H7 | low_cut | 15 | 1,435,693 | +11.6379% | 7,546 | 94,848 | 94,848 | 79,801 | 1,422,720 | +12,973 | 15 | +8.8827% | yes |
| H7 | low_cut | 100 | 9,486,369 | +637.6499% | 115 | 94,848 | 94,848 | 79,801 | 9,484,800 | +1,569 | 17 | +486.6955% | yes |
| H7 | high_cut | 1 | 1,253,765 | +0.0000% | 359,194 | 139,280 | 139,280 | 101,282 | 139,280 | +1,114,485 | 15 | +0.0000% | yes |
| H7 | high_cut | 15 | 2,100,506 | +67.5359% | 10,394 | 139,280 | 139,280 | 101,282 | 2,089,200 | +11,306 | 15 | +50.7687% | yes |
| H7 | high_cut | 100 | 13,928,097 | +1010.9017% | 1 | 139,280 | 139,280 | 101,282 | 13,928,000 | +97 | 17 | +759.9362% | yes |

## High-Cut versus Low-Cut Runtime

| molecule | precision | period | low-cut runtime | high-cut runtime | high vs low | cut increase |
|---|---:|---:|---:|---:|---:|---:|
| H4 | 1e-05 | 1 | 1,099,280 | 1,274,802 | +15.9670% | +2,772 |
| H4 | 1e-05 | 15 | 1,099,280 | 1,274,802 | +15.9670% | +2,772 |
| H4 | 1e-05 | 100 | 1,099,280 | 1,274,802 | +15.9670% | +2,772 |
| H4 | 1e-02 | 1 | 139,072 | 137,899 | -0.8434% | +2,772 |
| H4 | 1e-02 | 15 | 139,072 | 156,796 | +12.7445% | +2,772 |
| H4 | 1e-02 | 100 | 748,224 | 1,025,301 | +37.0313% | +2,772 |
| H7 | 1e-05 | 1 | 11,654,617 | 12,517,577 | +7.4044% | +44,432 |
| H7 | 1e-05 | 15 | 11,654,617 | 12,517,577 | +7.4044% | +44,432 |
| H7 | 1e-05 | 100 | 11,654,617 | 13,942,639 | +19.6319% | +44,432 |
| H7 | 1e-02 | 1 | 1,286,026 | 1,253,765 | -2.5086% | +44,432 |
| H7 | 1e-02 | 15 | 1,435,693 | 2,100,506 | +46.3061% | +44,432 |
| H7 | 1e-02 | 100 | 9,486,369 | 13,928,097 | +46.8222% | +44,432 |

## Validity and Execution

- QASM and optimized-IR hashes are fixed within each molecule/precision.
- Magic and measurement-feedback counts must match the source Dim2 compile. Their dependency depths may change under DistributedDim2 lowering and are treated as architecture-lowered metrics.
- Gate, magic, feedback, and entanglement count/depth must remain invariant when only entanglement-generation period changes.
- The compile-info schema exposes entanglement consumption and estimates, but not a direct no-entanglement-stock rejection counter.
- peak qret RSS: 4,501,536 KiB (4.29 GiB)
- maximum GNU-time swaps: 0
- execution: the first 18 cases ran sequentially with `MemoryHigh=44G`, `MemoryMax=48G`; the final six H7 `1e-2` cases ran with bounded six-way case parallelism under aggregate `MemoryHigh=32G`, `MemoryMax=40G`
- qret executable SHA-256: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- qret core library SHA-256: `9e39f84863d499ac71bd76c86cf88cb44d5d2e9416fb580bf6aba3aa9c49feb6`
