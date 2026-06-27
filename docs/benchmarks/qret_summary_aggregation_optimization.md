# qret Summary Aggregation Optimization

## Environment

- Evaluation HEAD at run start: `98d8f372c5be87aaf9f4e0ebe3e75c5ead42b5e3`
- qret executable hash used: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- qret core library hash used: `70e8fa9db1b723ba8a21a4854c8d6ff73b9d0c22461e30ac8ded17190871d7ff`
- qret core library path: `/home/abe/Project/Evaluation_grouped_surface_code/build/quration/cmake-build/quration-core/src/libqret-core.so.1.0.2`
- compiler: `c++ (Ubuntu 11.4.0-1ubuntu1~22.04) 11.4.0`
- platform: `Linux-6.8.0-47-generic-x86_64-with-glibc2.35`
- MemTotal KB: `65522476`
- SwapTotal KB: `2097148`
- compile mode: `ftqc_compile_topology`
- batch size: `2`
- sampling interval: `0.02` sec

## qret Hash Provenance

- build before executable hash: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- build before core hash: `70e8fa9db1b723ba8a21a4854c8d6ff73b9d0c22461e30ac8ded17190871d7ff`
- build after executable hash: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- build after core hash: `70e8fa9db1b723ba8a21a4854c8d6ff73b9d0c22461e30ac8ded17190871d7ff`
- executable hash changed by build: `False`
- core library hash changed by build: `False`

The qret executable is a small dynamically linked launcher. Most SC_LS_FIXED_V0 C++ changes live in `libqret-core.so`, so executable SHA-256 alone can stay unchanged after qret C++ changes. This run records both hashes and treats either changing during measurement as a failure.

## Time-Series Formula Audit

| field | element type | source | average | peak | sum use | derived metric |
| --- | --- | --- | --- | --- | --- | --- |
| `gate_throughput` | `uint64_t` | `time_series.GetInstructions(beat).size()` | `uint64_t` sum in beat order / runtime | max | no separate derived sum | throughput stats |
| `measurement_feedback_rate` | `uint64_t` | first use of measurement-created c-symbol, counted at `creation beat + StartCorrecting()` | counted-event sum / runtime | max sparse beat count | sum is counted feedback events | feedback stats |
| `magic_state_consumption_rate` | `uint64_t` | per-beat `UseMagicState()` count | `uint64_t` sum in beat order / runtime | max | no separate derived sum | magic consumption stats |
| `entanglement_consumption_rate` | `uint64_t` | per-beat `CountEntanglement()` | `uint64_t` sum in beat order / runtime | max | no separate derived sum | entanglement stats |
| `chip_cell_algorithmic_qubit` | `uint64_t` | `TimeSeries::ChipInfo::ChipCellAlgorithmicQubit()` | `uint64_t` sum in beat order / runtime | max | no | cell stats |
| `chip_cell_algorithmic_qubit_ratio` | `double` | algorithmic qubits / chip cells | `double` sum in beat order / runtime | max | no | ratio stats |
| `chip_cell_active_qubit_area` | `uint64_t` | used ancilla + algorithmic qubits | `uint64_t` sum in beat order / runtime | max | yes | `qubit_volume` |
| `chip_cell_active_qubit_area_ratio` | `double` | active area / chip cells | `double` sum in beat order / runtime | max | no | ratio stats |

## Isolated qret A/B

| case | variant | runs | median qret peak KB | median elapsed s | median compile_info B | max RSS stage |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| H4 `4th(new_2)` | `full` | 2 | 313534 | 3.133 | 18970408 | `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio` |
| H4 `4th(new_2)` | `summary_baseline` | 2 | 269674 | 3.111 | 2142 | `calc_info_with_topology_after_rate_fill` |
| H4 `4th(new_2)` | `summary_aggregate` | 3 | 249112 | 2.929 | 2142 | `calc_info_with_topology_after_summary_accumulation` |
| H5 `4th(new_2)` | `full` | 1 | 827328 | 8.690 | 60725194 | `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio` |
| H5 `4th(new_2)` | `summary_baseline` | 2 | 700314 | 8.419 | 2172 | `calc_info_with_topology_after_rate_fill` |
| H5 `4th(new_2)` | `summary_aggregate` | 2 | 641244 | 8.054 | 2172 | `calc_info_with_topology_after_summary_accumulation` |
| H6 `4th(new_2)` | `full` | 1 | 1799136 | 20.836 | 100210151 | `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio` |
| H6 `4th(new_2)` | `summary_baseline` | 2 | 1525224 | 19.928 | 2163 | `calc_info_with_topology_after_rate_fill` |
| H6 `4th(new_2)` | `summary_aggregate` | 2 | 1394628 | 19.185 | 2163 | `calc_info_with_topology_after_summary_accumulation` |

## Summary Aggregate Savings

| case | baseline peak KB | aggregate peak KB | saved KB | saved % |
| --- | ---: | ---: | ---: | ---: |
| H4 `4th(new_2)` | 269674 | 249112 | 20562 | 7.62 |
| H5 `4th(new_2)` | 700314 | 641244 | 59070 | 8.43 |
| H6 `4th(new_2)` | 1525224 | 1394628 | 130596 | 8.56 |

## End-to-End A/B

| case | variant | tree peak KB | qret peak KB | parent peak KB | parent at tree peak KB | qret at tree peak KB | read JSON sampled peak KB | compile_info B |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H5 `4th(new_2)` | `summary_baseline` | 1237560 | 708388 | 528148 | 528148 | 708132 | 528148 | 2172 |
| H5 `4th(new_2)` | `summary_aggregate` | 1176768 | 649384 | 526104 | 526104 | 649384 | 526104 | 2172 |
| H6 `4th(new_2)` | `summary_baseline` | 2066556 | 1538916 | 526616 | 526360 | 1538916 | 526616 | 2163 |
| H6 `4th(new_2)` | `summary_aggregate` | 1933864 | 1409016 | 523568 | 523568 | 1409016 | 523568 | 2163 |

## Semantic Comparisons

- `h4_4th_new2:summary_baseline`: normalized equal `True`, raw resource equal `True`, raw mismatches `[]`.
- `h4_4th_new2:summary_aggregate`: normalized equal `True`, raw resource equal `True`, raw mismatches `[]`.
- `h5_4th_new2:summary_baseline`: normalized equal `True`, raw resource equal `True`, raw mismatches `[]`.
- `h5_4th_new2:summary_aggregate`: normalized equal `True`, raw resource equal `True`, raw mismatches `[]`.
- `h6_4th_new2:summary_baseline`: normalized equal `True`, raw resource equal `True`, raw mismatches `[]`.
- `h6_4th_new2:summary_aggregate`: normalized equal `True`, raw resource equal `True`, raw mismatches `[]`.

## Correctness And Safety

- compact DepGraph marker on isolated runs: `True`
- pipeline-state output skipped on isolated runs: `True`
- all runs succeeded: `True`
- guard triggered: `False`
- maximum swap used KB: `1984216`
- minimum MemAvailable KB: `51713840`

## Execution Time Naming

`compile_info.json` field `execution_time_sec` is qret's physical execution-time estimate from QEC resource estimation. Evaluation-generated step metrics now preserve it as `estimated_execution_time_sec` and store wall-clock compile elapsed as `compile_wall_time_sec`. The legacy generated-step alias `execution_time_sec` remains wall-clock elapsed for existing consumers.

## Artifacts

- output root: `/home/abe/Project/Evaluation_grouped_surface_code/artifacts/qret_summary_aggregation`
- `results.jsonl`: one JSON object per run.
- `summary.csv`: compact spreadsheet table.
