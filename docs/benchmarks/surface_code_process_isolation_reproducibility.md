# Surface Code Process-Isolation Reproducibility

## Scope

- Evaluation baseline: `7c6c681b4bdf17cd9755b48d2d95c7d75ce3b074`.
- Evaluation HEAD at run: `7c6c681b4bdf17cd9755b48d2d95c7d75ce3b074`.
- H6 was not run.

## Call Graph Audit

| path | call sequence | notes |
|---|---|---|
| in-process prepare | `_prepare_in_process_only` -> `prepare_grouped_surface_code_step_artifact` | Generates one `SurfaceCodeStepArtifact`; cache root is explicit. |
| prepare worker | `_run_worker_subprocess(prepare)` -> `--worker prepare` -> `_worker_prepare` | Fresh Python process; writes result JSON and logs. |
| in-process compile | `_compile_artifact_in_process_only` -> `compile_prepared_surface_code_step_artifact` | Uses a prebuilt artifact; `reuse_cache=False`. |
| compile worker | `_run_worker_subprocess(compile)` -> `--worker compile` -> `_worker_compile` | Reconstructs the exact artifact manifest and verifies file hashes. |
| artifact serialization | `SurfaceCodeStepArtifact.to_dict` / `surface_code_step_artifact_from_dict` | Manifest contains paths and semantic scalars; semantic compare ignores temporary output path. |
| runtime/cache roots | `_surface_code_runtime` and per-run cache roots | Same-artifact compile shares input artifact; compile output roots are separated. |

## Same-Artifact Compile

| field | in-process | compile worker | equal |
|---|---|---|---:|
| qasm_hash | `89967a3bd69ee38c56...` | `89967a3bd69ee38c56...` | True |
| ir_hash | `20d52438c77e966956...` | `20d52438c77e966956...` | True |
| optimized_ir_hash | `e63a2a6e509e264fdc...` | `e63a2a6e509e264fdc...` | True |
| instruction_count | `401906` | `401906` | True |
| gate_depth | `236096` | `236096` | True |
| cache_key | `9dfb44be297052f8` | `9dfb44be297052f8` | True |
| qret_command | `qret compile --pip...` | `qret compile --pip...` | True |
| raw_metrics | `True` | `True` | True |
| normalized_metrics | `True` | `True` | True |
| returncode | `0` | `0` | True |

same-artifact compile all equal: `True`

## Prepare Reproducibility

| stage | in-process hash | worker hash | equal |
|---|---|---|---:|
| integral_scf_and_transform | `96836d02c364750397...` | `62b52c841dd84d3ba1...` | False |
| write_qasm | `68ce9f84d54960640f...` | `ea7cd58cf30ac443d3...` | False |
| qret_parse_or_ir_precision | `c9e3792ad770a259f4...` | `7e35d216c123118210...` | False |
| rz_helper_or_ir_optimization | `f57e8b0c61b163b393...` | `f3aea52ebc988f0845...` | False |
| optimized_ir_summary | `0bbe2b55ad5334a8bb...` | `458803ab9ce5b9461d...` | False |
| artifact_instruction_count | `401906` | `401762` | False |
| artifact_gate_depth | `236096` | `235772` | False |

## Environment Comparison

| setting | in-process | worker | equal |
|---|---|---|---:|
| same_artifact_compile:python_executable | `/home/abe/myproject/.venv/bin/py...` | `/home/abe/myproject/.venv/bin/py...` | True |
| same_artifact_compile:python_version | `3.11.1` | `3.11.1` | True |
| same_artifact_compile:working_directory | `/home/abe/Project/Evaluation_gro...` | `/home/abe/Project/Evaluation_gro...` | True |
| same_artifact_compile:surface_code_rz_helper_batch_size | `2` | `2` | True |
| same_artifact_compile:target_error | `0.00015936001019904` | `0.00015936001019904` | True |
| same_artifact_compile:step_time | `1.925283880931039` | `1.925283880931039` | True |
| same_artifact_compile:rotation_precision | `1e-05` | `1e-05` | True |
| same_artifact_compile:ham_name | `H4_sto-3g_singlet_distance_100_c...` | `H4_sto-3g_singlet_distance_100_c...` | True |
| same_artifact_compile:pf_label | `4th(new_2)` | `4th(new_2)` | True |
| same_artifact_compile:architecture_hash | `86a39ed1ff7c61ca4d94910f828aacd9...` | `86a39ed1ff7c61ca4d94910f828aacd9...` | True |
| same_artifact_compile:compile_mode | `ftqc_compile_topology` | `ftqc_compile_topology` | True |
| same_artifact_compile:topology_hash | `b7a81d54181fdc7985f026501290417a...` | `b7a81d54181fdc7985f026501290417a...` | True |
| same_artifact_compile:summary_mode | `summary` | `summary` | True |
| same_artifact_compile:inverse_map_release | `1` | `1` | True |
| same_artifact_compile:compact_dep_graph | `default_compact` | `default_compact` | True |
| same_artifact_compile:time_series_impl | `legacy_timeseries` | `legacy_timeseries` | True |
| same_artifact_compile:pipeline_state_output | `skipped` | `skipped` | True |
| same_artifact_compile:python_hash_seed | `` | `` | True |
| same_artifact_compile:python_random_seed | `not_used` | `not_used` | True |
| same_artifact_compile:numpy_random_seed | `not_used` | `not_used` | True |
| same_artifact_compile:qiskit_transpiler_seed | `not_used` | `not_used` | True |
| same_artifact_compile:rz_synthesis_seed | `not_used` | `not_used` | True |
| same_artifact_compile:env:PYTHONPATH | `` | `` | True |
| same_artifact_compile:env:PYTHONHASHSEED | `` | `` | True |
| same_artifact_compile:env:LANG | `ja_JP.UTF-8` | `ja_JP.UTF-8` | True |
| same_artifact_compile:env:LC_ALL | `C.UTF-8` | `C.UTF-8` | True |
| same_artifact_compile:env:LC_CTYPE | `C.UTF-8` | `C.UTF-8` | True |
| same_artifact_compile:env:OMP_NUM_THREADS | `` | `` | True |
| same_artifact_compile:env:OPENBLAS_NUM_THREADS | `` | `` | True |
| same_artifact_compile:env:MKL_NUM_THREADS | `` | `` | True |
| same_artifact_compile:env:SURFACE_CODE_RZ_HELPER_BATCH_SIZE | `` | `` | True |
| same_artifact_compile:env:QRET_SUMMARY_TIME_SERIES_IMPL | `` | `` | True |
| same_artifact_compile:env:QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING | `` | `` | True |
| same_artifact_compile:env:QRET_DEP_GRAPH_IMPL | `` | `` | True |
| prepare_reproducibility:python_executable | `/home/abe/myproject/.venv/bin/py...` | `/home/abe/myproject/.venv/bin/py...` | True |
| prepare_reproducibility:python_version | `3.11.1` | `3.11.1` | True |
| prepare_reproducibility:working_directory | `/home/abe/Project/Evaluation_gro...` | `/home/abe/Project/Evaluation_gro...` | True |
| prepare_reproducibility:surface_code_rz_helper_batch_size | `2` | `2` | True |
| prepare_reproducibility:target_error | `0.00015936001019904` | `0.00015936001019904` | True |
| prepare_reproducibility:step_time | `1.925283880931039` | `1.925283880931039` | True |
| prepare_reproducibility:rotation_precision | `1e-05` | `1e-05` | True |
| prepare_reproducibility:ham_name | `H4_sto-3g_singlet_distance_100_c...` | `H4_sto-3g_singlet_distance_100_c...` | True |
| prepare_reproducibility:pf_label | `4th(new_2)` | `4th(new_2)` | True |
| prepare_reproducibility:architecture_hash | `86a39ed1ff7c61ca4d94910f828aacd9...` | `86a39ed1ff7c61ca4d94910f828aacd9...` | True |
| prepare_reproducibility:compile_mode | `ftqc_compile_topology` | `ftqc_compile_topology` | True |
| prepare_reproducibility:topology_hash | `b7a81d54181fdc7985f026501290417a...` | `b7a81d54181fdc7985f026501290417a...` | True |
| prepare_reproducibility:summary_mode | `summary` | `summary` | True |
| prepare_reproducibility:inverse_map_release | `1` | `1` | True |
| prepare_reproducibility:compact_dep_graph | `default_compact` | `default_compact` | True |
| prepare_reproducibility:time_series_impl | `legacy_timeseries` | `legacy_timeseries` | True |
| prepare_reproducibility:pipeline_state_output | `skipped` | `skipped` | True |
| prepare_reproducibility:python_hash_seed | `` | `` | True |
| prepare_reproducibility:python_random_seed | `not_used` | `not_used` | True |
| prepare_reproducibility:numpy_random_seed | `not_used` | `not_used` | True |
| prepare_reproducibility:qiskit_transpiler_seed | `not_used` | `not_used` | True |
| prepare_reproducibility:rz_synthesis_seed | `not_used` | `not_used` | True |
| prepare_reproducibility:env:PYTHONPATH | `` | `` | True |
| prepare_reproducibility:env:PYTHONHASHSEED | `` | `` | True |
| prepare_reproducibility:env:LANG | `ja_JP.UTF-8` | `ja_JP.UTF-8` | True |
| prepare_reproducibility:env:LC_ALL | `C.UTF-8` | `C.UTF-8` | True |
| prepare_reproducibility:env:LC_CTYPE | `C.UTF-8` | `C.UTF-8` | True |
| prepare_reproducibility:env:OMP_NUM_THREADS | `` | `` | True |
| prepare_reproducibility:env:OPENBLAS_NUM_THREADS | `` | `` | True |
| prepare_reproducibility:env:MKL_NUM_THREADS | `` | `` | True |
| prepare_reproducibility:env:SURFACE_CODE_RZ_HELPER_BATCH_SIZE | `` | `` | True |
| prepare_reproducibility:env:QRET_SUMMARY_TIME_SERIES_IMPL | `` | `` | True |
| prepare_reproducibility:env:QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING | `` | `` | True |
| prepare_reproducibility:env:QRET_DEP_GRAPH_IMPL | `` | `` | True |

## Root Cause

```text
first divergent stage: integral_scf_and_transform
root cause: Independent cache-miss prepare recomputed PySCF/MO integrals with different low-bit floating values; persisted QASM/IR diverged before compile. This is prepare nondeterminism, not compile-worker isolation.
fix: No low-risk production fix applied. Deterministic MO canonicalization or integral-cache policy would be required and can change floating-point generation semantics.
```

## H4 End-To-End

Not run because prepare reproducibility was not accepted.

## H5 A/B

Not run because H4 acceptance did not pass.

## Final Answers

1. 同一artifact compileは一致したか: True.
2. compile worker分離自体は安全か: True.
3. prepareの最初の不一致stage: integral_scf_and_transform.
4. 不一致原因: Independent cache-miss prepare recomputed PySCF/MO integrals with different low-bit floating values; persisted QASM/IR diverged before compile. This is prepare nondeterminism, not compile-worker isolation.
5. seed/environment/orderのどれが原因だったか: floating-point/global numeric state.
6. 修正後H4 artifact hashは一致したか: not run.
7. raw metricsは一致したか: not run.
8. normalized metricsは一致したか: not run.
9. H5 A/Bを実行したか: False.
10. H5 tree peak削減量: not evaluated MB.
11. elapsed差: not evaluated.
12. process isolationをproduction defaultにしたか: False.
13. defaultにしなかった理由: H4 acceptance did not pass.
14. 次にqret ancilla/pathへ進むべきか: yes.
15. H6を実行していないこと: yes.

## qret Next Candidate

- `LATTICE_SURGERY_MAGIC` count: 236,736.
- Total estimated: 123.1 MB; operand 79.7 MB; ancilla/path 63.5 MB; all MachineFunction ancilla/path 68.4 MB.
- Next task candidates: path length distribution, duplicate path ratio, exact duplicate sequence ratio, shared prefix/suffix ratio, coordinate range, delta encoding, straight-line segment compression, `std::list` node overhead, routing insert/erase requirements, vector/pool/offset representation.

## Validation

- start pytest: 127 passed before changes
- start compileall and git diff --check: passed before changes
- start scripts/build_qret.sh and sha256sum: passed; qret d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5; lib 72ab48ae5227c325d5b0d236d3f48e115f04b37f8c07ac63f7445f72a3d6aa41
- repro diagnosis command: python3.11 scripts/profile_surface_code_lightweight_tree_memory.py --diagnose-reproducibility --sample-interval-sec 0.02 --batch-size 2; completed via saved summary after report-format fix
- same-artifact compile: artifact hashes, raw metrics, normalized metrics, cache semantics, qret command, and return code all equal
- prepare reproducibility: failed at integral_scf_and_transform; H4/H5 process-isolation A/B not run
- PYTHONPATH=src:. /home/abe/myproject/.venv/bin/python3.11 -m pytest -q: 132 passed
- /home/abe/myproject/.venv/bin/python3.11 -m compileall -q src scripts tests: passed
- git diff --check: passed
- scripts/build_qret.sh: passed
- sha256sum build/quration/qret build/quration/cmake-build/quration-core/src/libqret-core.so.1.0.2: qret d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5; lib 72ab48ae5227c325d5b0d236d3f48e115f04b37f8c07ac63f7445f72a3d6aa41
- target_sc_ls_fixed_v0_machine_function_inverse_map: 7 passed
- target_sc_ls_fixed_v0_compact_dep_graph: 9 passed
- target_sc_ls_fixed_v0_compile_info_output_mode: 5 passed
- target_sc_ls_fixed_v0_compile_info_summary_aggregation: 12 passed
- target_sc_ls_fixed_v0_compact_time_series: 6 passed
- target_sc_ls_fixed_v0_summary_event_sweep: 1 passed
- ctest --test-dir build/quration-tests --output-on-failure: 489/489 passed; existing skipped tests remained skipped
