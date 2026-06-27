# qret Compile Info Summary Output Optimization

## Environment

- Evaluation HEAD at run start: `28091a8baa2d286397ed88b988463bd852269798`
- dirty status at run start: `M .gitignore
 M src/trotterlib/architecture_sweep.py
 M src/trotterlib/config.py
 M src/trotterlib/surface_code.py
 M third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/calc_compile_info.cpp
 M third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/compile_info.cpp
 M third_party/quration/quration-core/src/qret/target/sc_ls_fixed_v0/compile_info.h
 M third_party/quration/quration-core/tests/CMakeLists.txt
?? scripts/profile_qret_compile_info_output_modes.py
?? tests/test_compile_info_output_modes.py
?? third_party/quration/quration-core/tests/target/sc_ls_fixed_v0/compile_info_output_mode.cpp`
- qret path: `/home/abe/Project/Evaluation_grouped_surface_code/build/quration/qret`
- qret SHA-256: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- compiler: `c++ (Ubuntu 11.4.0-1ubuntu1~22.04) 11.4.0`
- platform: `Linux-6.8.0-47-generic-x86_64-with-glibc2.35`
- MemTotal KB: `65522476`
- SwapTotal KB: `2097148`
- compile mode: `ftqc_compile_topology`
- topology: `/home/abe/Project/Evaluation_grouped_surface_code/third_party/quration/quration-core/examples/data/topology/tutorial.yaml`
- batch size: `2`
- sampling interval: `0.02` sec
- `QRET_DEP_GRAPH_IMPL`: `None` (unset means compact)
- pipeline-state output skip: `True`

## Consumer Audit

The eight time-series fields have the same consumer pattern in this repository:

| field | production metric full array use | `_ave` use | `_peak` use | report/visualization | public/API full array use | decision |
| --- | --- | --- | --- | --- | --- | --- |
| `gate_throughput` | no | yes, normalized when present | yes, normalized when present | historical reports mention files/stages only | yes, qret/pyqret full JSON schema | omit only in `summary`; keep in `full` |
| `measurement_feedback_rate` | no | yes, normalized when present | yes, normalized when present | historical reports mention files/stages only | yes, qret/pyqret full JSON schema | omit only in `summary`; keep in `full` |
| `magic_state_consumption_rate` | no | yes, normalized when present | yes, normalized when present | historical reports mention files/stages only | yes, qret/pyqret full JSON schema | omit only in `summary`; keep in `full` |
| `entanglement_consumption_rate` | no | yes, normalized when present | yes, normalized when present | historical reports mention files/stages only | yes, qret/pyqret full JSON schema | omit only in `summary`; keep in `full` |
| `chip_cell_algorithmic_qubit` | no | yes, normalized when present | yes, normalized when present | historical reports mention files/stages only | yes, qret/pyqret full JSON schema | omit only in `summary`; keep in `full` |
| `chip_cell_algorithmic_qubit_ratio` | no | yes, normalized when present | yes, normalized when present | historical reports mention files/stages only | yes, qret/pyqret full JSON schema | omit only in `summary`; keep in `full` |
| `chip_cell_active_qubit_area` | no | yes, normalized when present | yes, normalized when present | historical reports mention files/stages only | yes, qret/pyqret full JSON schema | omit only in `summary`; keep in `full` |
| `chip_cell_active_qubit_area_ratio` | no | yes, normalized when present | yes, normalized when present | historical reports mention files/stages only | yes, qret/pyqret full JSON schema | omit only in `summary`; keep in `full` |

| consumer | full array | ave | peak | existence/test only | report/visualization | production metric | note |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `surface_code_step_metrics_from_compile_info_json` -> `_load_compile_info_metrics_json` -> `normalize_surface_code_step_metrics` | no | yes | yes | no | no | yes | summary fields are enough for Evaluation metrics |
| `architecture_sweep._compile_info_row` | no | no | no | no | no | yes | uses scalar runtime, chip cells, qubit volume, physical qubits, code distance |
| compile cache payload/key | no | no | no | no | no | yes | mode is part of the cache key to avoid full/summary artifact reuse |
| benchmark/profiling scripts | no | no | no | stage markers/file sizes only | yes | no | use normalized metrics for correctness comparisons |
| docs and historical reports | no runtime read | no | no | yes | yes | no | textual references only |
| qret C++ `Json()` / `from_json` and pyqret bindings | yes | yes | yes | no | no | public API | qret default remains `full` for compatibility |
| tests | yes | yes | yes | yes | no | no | new tests cover both schemas and invalid mode |

Conclusion: Evaluation production resource evaluation does not require the full arrays. Public qret/pyqret consumers do, so the implementation keeps full output as the qret default and switches Evaluation production to explicit summary output.

## Design

- qret option: `sc_ls_fixed_v0_compile_info_output_mode` with values `full` and `summary`.
- qret default: `full`, preserving the existing JSON schema and pyqret/C++ full-array consumers.
- Evaluation default: `SurfaceCodeArchitecture.compile_info_output_mode='summary'` and pipeline YAML emits the option explicitly.
- `summary` omits the eight full time-series arrays and keeps scalar fields plus `_ave` and `_peak` fields.
- The compile cache key includes `compile_info_output_mode` so full and summary outputs cannot collide.
- Evaluation parser accepts both schemas; top-level metric extraction skips omitted arrays and still parses `gate_count_detail`.

## Isolated qret A/B

| case | mode | runs | median qret peak KB | min/max qret peak KB | median elapsed s | median compile_info B | max RSS stage |
| --- | --- | ---: | ---: | --- | ---: | ---: | --- |
| H4 `4th(new_2)` | `summary` | 3 | 270180 | 269876/270644 | 2.825 | 2142 | `calc_info_with_topology_after_cell_vector_resize` |
| H4 `4th(new_2)` | `full` | 3 | 313876 | 313148/314020 | 2.925 | 18970408 | `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio` |
| H5 `4th(new_2)` | `summary` | 2 | 701174 | 700928/701420 | 7.908 | 2172 | `calc_info_with_topology_after_cell_vector_resize` |
| H5 `4th(new_2)` | `full` | 2 | 827026 | 826868/827184 | 8.245 | 60725194 | `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio` |
| H6 `4th(new_2)` | `summary` | 2 | 1525938 | 1525648/1526228 | 18.820 | 2163 | `calc_info_with_topology_after_cell_vector_resize` |
| H6 `4th(new_2)` | `full` | 2 | 1777058 | 1776252/1777864 | 20.072 | 100210151 | `compile_info_json_after_assign_chip_cell_active_qubit_area_ratio` |

## Isolated Summary Savings

| case | qret peak full KB | qret peak summary KB | saved KB | saved % | compile_info full B | compile_info summary B | file saved % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H4 `4th(new_2)` | 313876 | 270180 | 43696 | 13.92 | 18970408 | 2142 | 99.99 |
| H5 `4th(new_2)` | 827026 | 701174 | 125852 | 15.22 | 60725194 | 2172 | 100.00 |
| H6 `4th(new_2)` | 1777058 | 1525938 | 251120 | 14.13 | 100210151 | 2163 | 100.00 |

## Key qret RSS Markers

| case | mode | routing KB | compact DepGraph KB | with topology exit KB | JSON DOM KB | full-array final KB | summary final KB | DOM destroyed KB | max marker KB |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H4 `4th(new_2)` | `summary` | 216884 | 244532 | 270644 | 270644 |  | 270644 | 270644 | 270644 |
| H4 `4th(new_2)` | `full` | 216228 | 243876 | 270244 | 303780 | 303780 |  | 270484 | 303780 |
| H5 `4th(new_2)` | `summary` | 548076 | 608492 | 701164 | 701164 |  | 701164 | 701164 | 701164 |
| H5 `4th(new_2)` | `full` | 548144 | 608560 | 701488 | 794160 | 794160 |  | 701564 | 794160 |
| H6 `4th(new_2)` | `summary` | 1188908 | 1320236 | 1525648 | 1474992 |  | 1474992 | 1474992 | 1525648 |
| H6 `4th(new_2)` | `full` | 1189384 | 1320968 | 1526832 | 1719496 | 1719496 |  | 1476172 | 1719496 |

## End-to-End Parent Process A/B

| case | mode | tree peak KB | qret peak KB | parent peak KB | parent at tree peak KB | qret at tree peak KB | read JSON sampled peak KB | read JSON delta KB | compile_info B |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H5 `4th(new_2)` | `summary` | 1220332 | 708116 | 510936 | 510936 | 708116 | 510936 | 0 | 2172 |
| H5 `4th(new_2)` | `full` | 1396124 | 885928 | 533576 | 508916 | 885928 | 627444 | 24660 | 60725194 |
| H6 `4th(new_2)` | `summary` | 2022140 | 1538980 | 481880 | 481880 | 1538980 | 481880 | 0 | 2163 |
| H6 `4th(new_2)` | `full` | 2300392 | 1838748 | 481632 | 478028 | 1821084 | 712636 | 234608 | 100210151 |

## End-to-End Summary Savings

| case | tree full KB | tree summary KB | tree saved KB | tree saved % | parent read full KB | parent read summary KB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H5 `4th(new_2)` | 1396124 | 1220332 | 175792 | 12.59 | 627444 | 510936 |
| H6 `4th(new_2)` | 2300392 | 2022140 | 278252 | 12.10 | 712636 | 481880 |

## Semantic A/B

- `h4_4th_new2` full vs summary normalized compile-info metrics equal: `True`; mismatches: `[]`; ignored: `['compile_info_json', 'execution_time_sec']`.
- `h5_4th_new2` full vs summary normalized compile-info metrics equal: `True`; mismatches: `[]`; ignored: `['compile_info_json', 'execution_time_sec']`.
- `h6_4th_new2` full vs summary normalized compile-info metrics equal: `True`; mismatches: `[]`; ignored: `['compile_info_json', 'execution_time_sec']`.

## Correctness And Safety

- isolated qret compact DepGraph marker on all runs: `True`
- isolated pipeline-state output skipped on all runs: `True`
- all recorded runs succeeded: `True`
- guard triggered: `False`
- maximum swap used KB: `1984232`
- minimum MemAvailable KB: `51401480`

## Final Answers

1. Evaluation production does not need the full compile-info arrays; it now emits summary compile-info by default.
2. qret keeps full output as the default for backward compatibility and public full-array consumers.
3. H4 semantic A/B compares full and summary normalized compile-info metrics; see `Semantic A/B`.
4. H5/H6 isolated qret and end-to-end parent-process A/B are recorded above.
5. The remaining peak, after summary mode, is outside full-array JSON duplication when the max marker is before or at compact/topology stages.

## Artifacts

- output root: `/home/abe/Project/Evaluation_grouped_surface_code/artifacts/qret_compile_info_output_modes`
- `results.jsonl`: one JSON object per run.
- `summary.csv`: compact table for quick spreadsheet checks.
- per-run directories contain `compile.yaml`, qret RSS JSONL, process-tree samples, stdout/stderr, and run summaries.

## Verification

- `PYTHONPATH=src /home/abe/myproject/.venv/bin/python3.11 -m pytest -q`: `67 passed`
- `/home/abe/myproject/.venv/bin/python3.11 -m compileall src scripts tests`: passed
- `git diff --check`: passed
- `scripts/build_qret.sh`: passed
- `/home/abe/.local/vcpkg/downloads/tools/cmake-4.2.3-linux/cmake-4.2.3-linux-x86_64/bin/cmake --build build/quration-tests --target target_sc_ls_fixed_v0_compile_info_output_mode target_sc_ls_fixed_v0_compact_dep_graph --parallel 2`: passed
- `./build/quration-tests/quration-core/tests/target_sc_ls_fixed_v0_compile_info_output_mode --gtest_color=no`: `5 passed`
- `./build/quration-tests/quration-core/tests/target_sc_ls_fixed_v0_compact_dep_graph --gtest_color=no`: `9 passed`
