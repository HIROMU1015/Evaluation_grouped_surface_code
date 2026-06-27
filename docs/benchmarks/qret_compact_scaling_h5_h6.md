# qret Compact Scaling H5/H6

## Environment

- Evaluation HEAD: `afeab0bfa8492809f9e16b7070fb273f13784705`
- qret SHA-256: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- qret build type: `Release`
- compiler: `c++ (Ubuntu 11.4.0-1ubuntu1~22.04) 11.4.0`
- MemTotal KB: `65522476`
- SwapTotal KB: `2097148`
- topology: `/home/abe/Project/Evaluation_grouped_surface_code/third_party/quration/quration-core/examples/data/topology/tutorial.yaml`
- PF: `4th(new_2)`
- batch size: `2`
- sampling interval: `0.02` sec

## Case Definitions

| case | Hamiltonian | basis | charge | spin/multiplicity | geometry | step time | target error | rotation precision | compile mode |
| --- | --- | --- | ---: | --- | --- | ---: | ---: | ---: | --- |
| H4 `4th(new_2)` | `H4_sto-3g_singlet_distance_100_charge_0_grouping` | sto-3g | 0 | singlet | linear H-chain, distance=1.0 | 1.92528 | 0.00015936 | 1e-05 | ftqc_compile_topology |
| H5 `4th(new_2)` | `H5_sto-3g_triplet_1+_distance_100_charge_1_grouping` | sto-3g | 1 | triplet 1+ | linear H-chain, distance=1.0 | 2.16213 | 0.00015936 | 1e-05 | ftqc_compile_topology |
| H6 `4th(new_2)` | `H6_sto-3g_singlet_distance_100_charge_0_grouping` | sto-3g | 0 | singlet | linear H-chain, distance=1.0 | 1.8137 | 0.00015936 | 1e-05 | ftqc_compile_topology |

## End-to-End Results

| case | status | parent peak KB | qret peak KB | tree peak KB | elapsed s | final metrics |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| H4 `4th(new_2)` | ok | 352280 | 319116 | 643836 | 28.562 | yes |
| H5 `4th(new_2)` | ok | 506892 | 885940 | 1325204 | 66.993 | yes |
| H6 `4th(new_2)` | ok | 864792 | 1840180 | 2395632 | 141.672 | yes |

## Isolated qret Results

| case | runs | median peak KB | min/max peak KB | median elapsed s | max-RSS stage |
| --- | ---: | ---: | --- | ---: | --- |
| H4 `4th(new_2)` | 3 | 313600 | 313596/313784 | 2.921 | `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio` |
| H5 `4th(new_2)` | 2 | 826958.0 | 826920/826996 | 8.050 | `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio` |
| H6 `4th(new_2)` | 2 | 1799528.0 | 1799264/1799792 | 19.493 | `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio` |

## Scaling

| case | optimized instructions | machine instructions | nodes | edges | compact payload B | qret peak KB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H4 `4th(new_2)` | 401762 | 570306 | 570306 | 581750 | 29728272 | 313596 |
| H5 `4th(new_2)` | 1063500 | 1499072 | 1499072 | 1533838 | 62324224 | 826920 |
| H6 `4th(new_2)` | 2378540 | 3317310 | 3317310 | 3404886 | 127201776 | 1799792 |

## Normalized Scaling

| case | median qret peak / machine inst KB | routing RSS / machine inst KB | compact payload / node B | optimized IR / optimized inst B | compile_info JSON B |
| --- | ---: | ---: | ---: | ---: | ---: |
| H4 `4th(new_2)` | 0.5499 | 0.3788 | 52.13 | 21.69 | 18966758 |
| H5 `4th(new_2)` | 0.5516 | 0.3657 | 41.58 | 21.74 | 60725194 |
| H6 `4th(new_2)` | 0.5425 | 0.3586 | 38.34 | 21.88 | 100123931 |

## Ratio Summary

| transition | optimized inst | machine inst | median qret peak | end-to-end tree peak | compact payload | compile_info JSON |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H4 `4th(new_2)` -> H5 `4th(new_2)` | 2.647 | 2.629 | 2.637 | 2.058 | 2.096 | 3.202 |
| H5 `4th(new_2)` -> H6 `4th(new_2)` | 2.237 | 2.213 | 2.176 | 1.808 | 2.041 | 1.649 |
| H4 `4th(new_2)` -> H6 `4th(new_2)` | 5.920 | 5.817 | 5.738 | 3.721 | 4.279 | 5.279 |

## Stage Breakdown

| case | stage | current RSS KB | delta KB | elapsed s |
| --- | --- | ---: | ---: | ---: |
| H4 `4th(new_2)` | `read_compile_info_json` | 643836 |  | 28.562 |
| H4 `4th(new_2)` | `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio` | 303356 | 6656 | 2.935 |
| H4 `4th(new_2)` | `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio` | 303360 | 6656 | 2.921 |
| H4 `4th(new_2)` | `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio` | 303288 | 6656 | 2.847 |
| H5 `4th(new_2)` | `qret_compile` | 1325204 |  | 66.993 |
| H5 `4th(new_2)` | `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio` | 793896 | 18688 | 8.016 |
| H5 `4th(new_2)` | `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio` | 793716 | 18688 | 8.085 |
| H6 `4th(new_2)` | `qret_compile` | 2395632 |  | 141.672 |
| H6 `4th(new_2)` | `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio` | 1759344 | 40448 | 19.649 |
| H6 `4th(new_2)` | `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio` | 1758816 | 40448 | 19.336 |

## Key qret RSS Markers

| case | load JSON alive KB | after lowering KB | routing after main loop KB | after compact DepGraph KB | with topology exit KB | after JSON DOM KB | max marker KB | GNU maxrss KB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H4 `4th(new_2)` | 146072 | 169604 | 216060 | 243708 | 269820 | 303356 | 303356 | 313596 |
| H5 `4th(new_2)` | 371096 | 430888 | 548136 | 608296 | 700968 | 793896 | 793896 | 826920 |
| H6 `4th(new_2)` | 819872 | 944008 | 1189576 | 1316808 | 1525532 | 1759344 | 1759344 | 1799792 |

## Correctness Checks

- compact DepGraph implementation marker on isolated qret runs: `True`
- DepGraph topological-order invariant on isolated qret runs: `True`
- pipeline-state output skipped on isolated qret runs: `True`
- pipeline-state output absent on isolated qret runs: `True`
- compile_info JSON emitted for isolated qret runs: `True`
- H5/H6 legacy DepGraph runs: `not run`; current production compact configuration only.

## Safety

- minimum MemAvailable KB: `50964796`
- maximum swap used KB: `1984232`
- maximum SwapFree drop KB during a run: `0`
- guard triggered: `False`
- H6 decision: `run`
- H6 decision failed conditions: `[]`

## Determinism

- `h4_4th_new2` isolated qret normalized metrics equal: `True`, semantic fields equal: `True`
- `h5_4th_new2` isolated qret normalized metrics equal: `True`, semantic fields equal: `True`
- `h6_4th_new2` isolated qret normalized metrics equal: `True`, semantic fields equal: `True`

## Final Answers

1. H5 completed: `True`.
2. H6 completed: `True`.
3. H5 qret peak RSS: `826958.0` KB median isolated.
4. H6 qret peak RSS: `1799528.0` KB median isolated.
5. H5/H6 process tree peak: `1325204` / `2395632` KB end-to-end.
6. H4->H5->H6 qret peak: `313600` -> `826958.0` -> `1799528.0` KB.
7. Compact DepGraph payload scales below qret peak RSS in these three points; see Normalized Scaling and Ratio Summary. Treat this as observed scaling, not a proven complexity fit.
8. qret max RSS stages: H5 `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio`, H6 `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio`.
9. end-to-end max RSS stages: H5 `qret_compile`, H6 `qret_compile`.
10. New bottleneck classification: `F` for the end-to-end process-tree peak. The qret-only max marker is compile-info JSON DOM materialization/final field insertion after compact DepGraph, which is `G` if the qret-only stage must be mapped to A-G.
11. Current implementation stable for H6: `True`.
12. End-to-end peak is still the qret_compile process window; H6 shows Python parent and qret child residency overlap, so classify the end-to-end limiter as process overlap plus qret JSON output peak.
13. Before H7+, profile the compile_info JSON DOM creation path first, then reduce Evaluation parent residency during qret_compile if process-tree RSS remains the limiter.
14. Production optimization added in this run: `false`; only profiling/report/test changes are intended.
15. Failed cases: see summary JSON; direct cause is recorded in each failed row's `error` field.
