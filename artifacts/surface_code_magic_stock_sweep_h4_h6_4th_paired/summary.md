# H4-H6 Paired-Precision Dim2 Magic-Stock Sweep

Each molecule/precision uses one fixed optimized IR and one fixed 10x10 Dim2 topology with four central factories, 96 usable non-factory cells, and two initial egress cells per factory. Only qret's maximum magic-state stock changes. Absolute runtime is not compared across precision as an architecture effect.

## rotation_precision=1e-05

| molecule | stock | runtime | vs stock 10000 | marginal reduction | runtime no topology | topology overhead | code distance | physical qubits | QV vs stock 10000 | workload match |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| H4 | 1 | 848,791 | +4.2633% | reference | 841,266 | +7,525 | 13 | 32,448 | +6.3568% | yes |
| H4 | 4 | 837,004 | +2.8154% | +1.3887% | 837,079 | -75 | 13 | 32,448 | +4.7263% | yes |
| H4 | 16 | 829,234 | +1.8610% | +0.9283% | 830,045 | -811 | 13 | 32,448 | +3.4675% | yes |
| H4 | 64 | 816,874 | +0.3427% | +1.4905% | 817,698 | -824 | 13 | 32,448 | +1.6364% | yes |
| H4 | 10000 | 814,084 | +0.0000% | +0.3415% | 814,083 | +1 | 13 | 32,448 | +0.0000% | yes |
| H5 | 1 | 2,202,143 | +3.7625% | reference | 2,182,791 | +19,352 | 15 | 43,200 | +5.5175% | yes |
| H5 | 4 | 2,169,888 | +2.2427% | +1.4647% | 2,171,006 | -1,118 | 15 | 43,200 | +3.8785% | yes |
| H5 | 16 | 2,150,811 | +1.3438% | +0.8792% | 2,153,486 | -2,675 | 15 | 43,200 | +2.7249% | yes |
| H5 | 64 | 2,125,710 | +0.1611% | +1.1670% | 2,126,386 | -676 | 15 | 43,200 | +1.2030% | yes |
| H5 | 10000 | 2,122,291 | +0.0000% | +0.1608% | 2,122,265 | +26 | 15 | 43,200 | +0.0000% | yes |
| H6 | 1 | 4,755,431 | +3.9145% | reference | 4,712,551 | +42,880 | 15 | 43,200 | +5.2427% | yes |
| H6 | 4 | 4,686,355 | +2.4051% | +1.4526% | 4,686,780 | -425 | 15 | 43,200 | +3.6564% | yes |
| H6 | 16 | 4,639,459 | +1.3804% | +1.0007% | 4,645,886 | -6,427 | 15 | 43,200 | +2.4454% | yes |
| H6 | 64 | 4,580,916 | +0.1011% | +1.2618% | 4,583,817 | -2,901 | 15 | 43,200 | +1.0135% | yes |
| H6 | 10000 | 4,576,290 | +0.0000% | +0.1010% | 4,576,285 | +5 | 15 | 43,200 | +0.0000% | yes |

## rotation_precision=1e-02

| molecule | stock | runtime | vs stock 10000 | marginal reduction | runtime no topology | topology overhead | code distance | physical qubits | QV vs stock 10000 | workload match |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| H4 | 1 | 149,605 | +2.1822% | reference | 148,957 | +648 | 13 | 32,448 | +2.4612% | yes |
| H4 | 4 | 148,413 | +1.3681% | +0.7968% | 148,286 | +127 | 13 | 32,448 | +1.6711% | yes |
| H4 | 16 | 146,848 | +0.2992% | +1.0545% | 147,015 | -167 | 13 | 32,448 | +0.6150% | yes |
| H4 | 64 | 146,410 | +0.0000% | +0.2983% | 146,409 | +1 | 13 | 32,448 | +0.0844% | yes |
| H4 | 10000 | 146,410 | +0.0000% | +0.0000% | 146,409 | +1 | 13 | 32,448 | +0.0000% | yes |
| H5 | 1 | 366,650 | +1.1973% | reference | 365,473 | +1,177 | 13 | 32,448 | +1.3782% | yes |
| H5 | 4 | 364,648 | +0.6447% | +0.5460% | 364,672 | -24 | 13 | 32,448 | +0.8537% | yes |
| H5 | 16 | 362,636 | +0.0894% | +0.5518% | 362,952 | -316 | 13 | 32,448 | +0.2686% | yes |
| H5 | 64 | 362,312 | +0.0000% | +0.0893% | 362,311 | +1 | 13 | 32,448 | +0.0566% | yes |
| H5 | 10000 | 362,312 | +0.0000% | +0.0000% | 362,311 | +1 | 13 | 32,448 | +0.0000% | yes |
| H6 | 1 | 717,483 | +0.6434% | reference | 716,362 | +1,121 | 15 | 43,200 | +0.6681% | yes |
| H6 | 4 | 715,656 | +0.3872% | +0.2546% | 715,535 | +121 | 15 | 43,200 | +0.4456% | yes |
| H6 | 16 | 713,377 | +0.0675% | +0.3184% | 713,805 | -428 | 15 | 43,200 | +0.1420% | yes |
| H6 | 64 | 712,896 | +0.0000% | +0.0674% | 713,072 | -176 | 15 | 43,200 | +0.0303% | yes |
| H6 | 10000 | 712,896 | +0.0000% | +0.0000% | 713,072 | -176 | 15 | 43,200 | +0.0000% | yes |

## Saturation at < 1.0% Runtime Difference

| molecule | saturation stock at 1e-5 | saturation stock at 1e-2 | stock 64 penalty at 1e-5 | stock 64 penalty at 1e-2 |
|---|---:|---:|---:|---:|
| H4 | 64 | 16 | +0.3427% | +0.0000% |
| H5 | 64 | 4 | +0.1611% | +0.0000% |
| H6 | 64 | 1 | +0.1011% | +0.0000% |

## Validity and Execution

- QASM, optimized IR, topology, factory count/coordinates, magic generation period, reaction time, and QEC inputs are fixed within each molecule/precision.
- Non-factory gate counts/depths and magic/feedback demand must match in every stock case.
- The standard compile-info schema does not expose a direct no-magic-stock rejection count; runtime response is the primary saturation evidence.
- Code-distance changes, if present, affect physical qubits/QV but not the primary beat-runtime comparison.
- additional stock 256/1024 required: no
- H7 follow-up required by the predeclared saturation/size-trend rule: no
- peak qret RSS: 1,738,976 KiB (1.66 GiB)
- maximum GNU-time swaps: 0
- qret executable SHA-256: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- qret core library SHA-256: `9e39f84863d499ac71bd76c86cf88cb44d5d2e9416fb580bf6aba3aa9c49feb6`
