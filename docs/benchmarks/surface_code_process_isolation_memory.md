# Surface Code Process Isolation Memory

## Profiling Overhead Audit

| feature | light | deep | estimated overhead |
|---|---|---|---:|
| tracemalloc.start() | off | on | RSS: high; metadata tracked for Python allocations; elapsed: medium-high during allocation-heavy prepare |
| gc.get_objects() | off | on | RSS: low direct, can perturb caches; elapsed: medium when repeated at markers |
| recursive object size estimator | off | on | RSS: medium from traversal bookkeeping; elapsed: medium-high on nested objects |
| NumPy/pandas deep-size traversal | off | on | RSS: low-medium; elapsed: medium if large containers are present |
| all parent marker object audit | off | on | RSS: medium; elapsed: medium |
| process sample memory retention | off | off | RSS: none in current streaming samplers; elapsed: low |
| raw sample history list | off | off | RSS: none in current streaming samplers; elapsed: none |
| JSON serialization buffer | on | on | RSS: low; one row at a time; elapsed: low at 20 ms sampling |

## Lightweight Baseline

| metric | value |
|---|---:|
| prepare peak KB | 444,152 |
| qret launch before parent KB | 381,532 |
| tree peak KB | 953,784 |
| parent at tree peak KB | 381,532 |
| qret at tree peak KB | 572,252 |
| elapsed sec | 68.359 |

## Comparison With Deep Profiling

| metric | light | deep | difference |
|---|---:|---:|---:|
| tree peak KB | 953,784 | 1,231,464 | -277,680 |
| parent at tree peak KB | 381,532 | 658,528 | -276,996 |
| elapsed sec | 68.359 | 199.274 | -130.915 |

## Gate Decision

process isolation gate passed: `True`
reasons: `qret_launch_parent_rss_ge_300mb, parent_share_at_tree_peak_ge_30pct, prepare_delta_ge_200mb`

## Process-Isolation A/B

Not run because H4 semantic correctness failed.


## H4 Correctness

| variant | tree peak KB | qret peak KB | elapsed sec |
|---|---:|---:|---:|
| in_process | 546,072 | 226,204 | 28.398 |
| process_isolated | 558,312 | 226,496 | 29.386 |

- artifact hashes equal: `False`
- raw qret metrics equal: `False`
- normalized metrics equal: `False`

## Semantic Comparison

```text
{
  "h4": {
    "artifact_hashes": {
      "all_equal": false,
      "field_count": 9,
      "ignored_fields": [],
      "mismatches": [
        "cache_key",
        "gate_depth",
        "instruction_count",
        "ir_hash",
        "optimized_ir_hash",
        "qasm_hash"
      ]
    },
    "normalized_metrics": {
      "all_equal": false,
      "field_count": 57,
      "ignored_fields": [],
      "mismatches": [
        "cache_key",
        "chip_cell_active_qubit_area_ave",
        "chip_cell_active_qubit_area_ratio_ave",
        "chip_cell_algorithmic_qubit_ave",
        "chip_cell_algorithmic_qubit_ratio_ave",
        "gate_count",
        "gate_depth",
        "gate_throughput_ave",
        "gate_throughput_peak",
        "magic_state_consumption_rate_ave",
        "measurement_feedback_rate_ave",
        "optimized_ir_hash",
        "qasm_hash",
        "qubit_volume",
        "runtime",
        "runtime_without_topology",
        "rz_call_cache",
        "step_magic_state_depth"
      ]
    },
    "raw_metrics": {
      "all_equal": false,
      "field_count": 31,
      "ignored_fields": [
        "compile_info_json",
        "compile_wall_time_sec",
        "execution_time_sec"
      ],
      "mismatches": [
        "chip_cell_active_qubit_area_ave",
        "chip_cell_active_qubit_area_ratio_ave",
        "chip_cell_algorithmic_qubit_ave",
        "chip_cell_algorithmic_qubit_ratio_ave",
        "gate_count",
        "gate_count_dict",
        "gate_depth",
        "gate_throughput_ave",
        "gate_throughput_peak",
        "magic_state_consumption_rate_ave",
        "measurement_feedback_rate_ave",
        "qubit_volume",
        "runtime",
        "runtime_without_topology"
      ]
    }
  }
}
```

## Final Answers

1. tracemallocなしH5 tree peak: 931.4 MB.
2. deep profileとの差: -271.2 MB.
3. qret起動前parent RSS: 372.6 MB.
4. parent gate: True (qret_launch_parent_rss_ge_300mb, parent_share_at_tree_peak_ge_30pct, prepare_delta_ge_200mb).
5. prepare後retained memory: 331.6 MB observed.
6. process分離実装: True.
7. process分離tree peak削減: not evaluated MB.
8. qret peak変化: not evaluated KB.
9. elapsed差: not evaluated.
10. artifact hashes一致: False.
11. raw metrics一致: False.
12. normalized metrics一致: False.
13. process分離production default: False.
14. defaultにしなかった理由: H4 semantic correctness failed; H5 A/B was not run.
15. 次はqret `LATTICE_SURGERY_MAGIC` operand/ancilla/path監査を推奨: yes
16. H6は実行していません。

## qret Next Candidate

- `LATTICE_SURGERY_MAGIC` count: 236,736.
- Total estimated: 123.1 MB; operand 79.7 MB; ancilla/path 63.5 MB.
- Next audit should inspect duplicate paths, path length distribution, coordinate ranges, consecutive path compression, `std::list` node overhead, routing-time operations, random insertion/erase requirements, and vector/small-vector/pool options.

## Validation

- `PYTHONPATH=src:. /home/abe/myproject/.venv/bin/python3.11 -m pytest -q`: 127 passed.
- `/home/abe/myproject/.venv/bin/python3.11 -m compileall -q src scripts tests`: passed.
- `git diff --check`: passed.
- `scripts/build_qret.sh`: passed.
- `sha256sum build/quration/qret build/quration/cmake-build/quration-core/src/libqret-core.so.1.0.2`: qret `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`; lib `72ab48ae5227c325d5b0d236d3f48e115f04b37f8c07ac63f7445f72a3d6aa41`.
- `target_sc_ls_fixed_v0_machine_function_inverse_map --gtest_color=no`: 7 passed.
- `target_sc_ls_fixed_v0_compact_dep_graph --gtest_color=no`: 9 passed.
- `target_sc_ls_fixed_v0_compile_info_output_mode --gtest_color=no`: 5 passed.
- `target_sc_ls_fixed_v0_compile_info_summary_aggregation --gtest_color=no`: 12 passed.
- `target_sc_ls_fixed_v0_compact_time_series --gtest_color=no`: 6 passed.
- `target_sc_ls_fixed_v0_summary_event_sweep --gtest_color=no`: 1 passed.
- `ctest --test-dir build/quration-tests --output-on-failure`: 489/489 passed; existing skipped tests remained skipped.
