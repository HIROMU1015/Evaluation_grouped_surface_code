# H4-H7 Cheap-RZ Dim2 Magic-Generation-Period Sweep

Each molecule uses one fixed optimized IR and one fixed 10x10 Dim2 topology with four central factories, stock 10000, reaction time 1, 96 usable non-factory cells, and two initial egress cells per factory. Only qret's magic-generation period changes.

- rotation precision: `1e-02`
- period 1: ideal fast-supply reference
- period 15: current standard Dim2 baseline

## H4

| period | runtime | vs period 1 | vs period 15 | change vs previous | runtime no topology | topology overhead | code distance | physical qubits | QV vs period 15 | workload match |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 145,741 | +0.0000% | -0.4569% | reference | 145,740 | +1 | 13 | 32,448 | -0.3425% | yes |
| 4 | 145,744 | +0.0021% | -0.4549% | +0.0021% | 145,783 | -39 | 13 | 32,448 | -0.3418% | yes |
| 15 | 146,410 | +0.4590% | +0.0000% | +0.4570% | 146,409 | +1 | 13 | 32,448 | +0.0000% | yes |
| 30 | 151,382 | +3.8706% | +3.3959% | +3.3959% | 151,381 | +1 | 13 | 32,448 | +2.1555% | yes |
| 100 | 292,930 | +100.9935% | +100.0751% | +93.5039% | 292,929 | +1 | 13 | 32,448 | +71.4470% | yes |

## H5

| period | runtime | vs period 1 | vs period 15 | change vs previous | runtime no topology | topology overhead | code distance | physical qubits | QV vs period 15 | workload match |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 361,685 | +0.0000% | -0.1731% | reference | 361,684 | +1 | 13 | 32,448 | -0.1447% | yes |
| 4 | 361,686 | +0.0003% | -0.1728% | +0.0003% | 361,723 | -37 | 13 | 32,448 | -0.1447% | yes |
| 15 | 362,312 | +0.1734% | +0.0000% | +0.1731% | 362,311 | +1 | 13 | 32,448 | +0.0000% | yes |
| 30 | 369,624 | +2.1950% | +2.0182% | +2.0182% | 369,623 | +1 | 13 | 32,448 | +1.3648% | yes |
| 100 | 481,458 | +33.1153% | +32.8849% | +30.2562% | 481,457 | +1 | 13 | 32,448 | +24.3318% | yes |

## H6

| period | runtime | vs period 1 | vs period 15 | change vs previous | runtime no topology | topology overhead | code distance | physical qubits | QV vs period 15 | workload match |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 712,255 | +0.0000% | -0.0899% | reference | 712,254 | +1 | 15 | 43,200 | -0.0584% | yes |
| 4 | 712,258 | +0.0004% | -0.0895% | +0.0004% | 712,331 | -73 | 15 | 43,200 | -0.0584% | yes |
| 15 | 712,896 | +0.0900% | +0.0000% | +0.0896% | 713,072 | -176 | 15 | 43,200 | +0.0000% | yes |
| 30 | 723,832 | +1.6254% | +1.5340% | +1.5340% | 723,831 | +1 | 15 | 43,200 | +1.0595% | yes |
| 100 | 775,912 | +8.9374% | +8.8394% | +7.1950% | 775,911 | +1 | 15 | 43,200 | +6.0507% | yes |

## H7

| period | runtime | vs period 1 | vs period 15 | change vs previous | runtime no topology | topology overhead | code distance | physical qubits | QV vs period 15 | workload match |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 1,385,272 | +0.0000% | -0.0437% | reference | 1,384,426 | +846 | 15 | 43,200 | -0.0301% | yes |
| 4 | 1,385,275 | +0.0002% | -0.0434% | +0.0002% | 1,384,499 | +776 | 15 | 43,200 | -0.0301% | yes |
| 15 | 1,385,877 | +0.0437% | +0.0000% | +0.0435% | 1,385,193 | +684 | 15 | 43,200 | +0.0000% | yes |
| 30 | 1,400,287 | +1.0839% | +1.0398% | +1.0398% | 1,399,441 | +846 | 15 | 43,200 | +0.7438% | yes |
| 100 | 1,470,357 | +6.1421% | +6.0958% | +5.0040% | 1,469,511 | +846 | 15 | 43,200 | +4.3175% | yes |

## Sensitivity Summary

| molecule | period 15 vs 1 | period 30 vs 15 | period 100 vs 15 | full runtime spread |
|---|---:|---:|---:|---:|
| H4 | +0.4590% | +3.3959% | +100.0751% | 100.9935% |
| H5 | +0.1734% | +2.0182% | +32.8849% | 33.1153% |
| H6 | +0.0900% | +1.5340% | +8.8394% | 8.9374% |
| H7 | +0.0437% | +1.0398% | +6.0958% | 6.1421% |

## Validity and Execution

- QASM, optimized IR, topology, factory count/coordinates, maximum magic-state stock, reaction time, and QEC inputs are fixed within each molecule.
- Non-factory gate counts/depths and magic/feedback demand must match in every period case.
- `runtime_estimation_magic_state_consumption_count/depth` are period-scaled supply-time estimates, so they are recorded but excluded from the fixed logical-workload invariant.
- material runtime threshold: 1.0% versus period 15 at H6 period 30/100
- H7 follow-up required: yes
- H7 follow-up complete: yes
- H7 trigger: H6 period=30: +1.5340% vs period=15; H6 period=100: +8.8394% vs period=15
- peak qret RSS: 961,516 KiB (0.92 GiB)
- maximum GNU-time swaps: 0
- qret executable SHA-256: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- qret core library SHA-256: `9e39f84863d499ac71bd76c86cf88cb44d5d2e9416fb580bf6aba3aa9c49feb6`
