# Surface Code Parent Memory Optimization

## Scope

- Evaluation HEAD: `a489dbcdc11232ac144191defb7861dc765a9961`
- Required baseline: `a489dbcdc11232ac144191defb7861dc765a9961`
- H6 was not run. This script rejects H6 cases.
- Measurement target: H5 `4th(new_2)`, batch size 2, cache miss, topology compile.
- Production settings: summary compile-info output, summary legacy TimeSeries, compact DepGraph default, inverse-map release enabled, pipeline-state output skipped.

## H5 End-to-End Baseline

| metric | KB | MB |
|---|---:|---:|
| process tree peak | 1,231,464 | 1202.6 |
| qret at tree peak | 572,936 | 559.5 |
| Python parent at tree peak | 658,528 | 643.1 |
| other children at tree peak | 0 | 0.0 |
| parent peak | 726,692 | 709.7 |
| qret peak | 572,936 | 559.5 |
| qret `/usr/bin/time` max RSS | 571,656 | 558.3 |
| read compile-info sampled peak | 658,528 | 643.1 |
| prepare artifact stage peak | 726,948 | 709.9 |
| compile stage peak | 658,528 | 643.1 |

- Tree peak sample index: `1727`
- Elapsed: `199.274` seconds
- Compile-info size: `2,172` bytes
- qret stdout/stderr captured bytes: `4284`
- Max Python RSS stage: `prepare/prepare_rz_helper_overrides` at `726,948` KB.
- Compile stage peak: `compile_cache_lookup` at `658,528` KB.

## qret Window

| marker | parent RSS KB | parent RSS MB |
|---|---:|---:|
| before qret launch | 658,528 | 643.1 |
| after qret launch | 658,528 | 643.1 |
| before qret exit | 658,528 | 643.1 |
| after qret exit | 658,528 | 643.1 |
| increase during qret | 0 | 0.0 |

- Selected qret window: `contains_tree_peak_sample` from `201` qret-active windows.

## Gate Decision

- Gate passed: `True`
- Reasons: `parent_at_tree_peak_ge_200mb, parent_share_ge_25pct`
- Parent share at tree peak: `53.48%`

## Parent Object Audit

The object audit is taken from Evaluation's parent process immediately before the qret compile call. Internal prepare-stage Hamiltonian/circuit objects are not retained by the driver after `prepare_grouped_surface_code_step_artifact` returns; their RSS is represented by prepare stage metrics rather than a live Python object reference at qret launch.

| object | type | recursive bytes | NumPy bytes | pandas bytes |
|---|---|---:|---:|---:|
| artifact | SurfaceCodeStepArtifact | 1,162,624 | 0 | 0 |
| sample_marker_history | list | 20,717 | 0 | 0 |
| compile_request_architecture | dict | 2,424 | 0 | 0 |
| optimized_ir_path_text | str | 294 | 0 | 0 |

qret launch parent marker:

| field | KB | MB |
|---|---:|---:|
| RSS | 658,528 | 643.1 |
| PSS | 651,958 | 636.7 |
| PrivateDirty | 576,836 | 563.3 |
| tracemalloc current | 151,470 | 147.9 |
| tracemalloc peak | 270,607 | 264.3 |

The live Python object estimates are far smaller than parent RSS at qret launch, and tracemalloc current is also well below RSS. That points to native-library/import footprint, allocator retention, and earlier prepare-stage work rather than a single large live Python container that can be dropped safely before qret compile.

## Decision

- No Python parent production change was adopted in this run.
- The gate passed, but this profile did not identify a low-risk live parent object with a credible 50 MB reduction at qret launch.
- Next qret-side candidate: reduce `LATTICE_SURGERY_MAGIC` operand/ancilla/path representation memory.

## Validation

- Python: `PYTHONPATH=src:. /home/abe/myproject/.venv/bin/python3.11 -m pytest -q` -> 112 passed.
- Python compile: `/home/abe/myproject/.venv/bin/python3.11 -m compileall -q src scripts tests` -> passed.
- Diff hygiene: `git diff --check` -> passed.
- qret targeted tests: inverse map, compact DepGraph, compile-info output/summary aggregation, compact TimeSeries parity, summary event sweep -> passed.
- qret full CTest: `/home/abe/.local/vcpkg/downloads/tools/cmake-4.2.3-linux/cmake-4.2.3-linux-x86_64/bin/ctest --test-dir build/quration-tests --output-on-failure` -> 489 tests passed, 0 failed; CTest-reported skips unchanged.
- H6 was not run.

## Artifacts

- Summary: `/home/abe/Project/Evaluation_grouped_surface_code/artifacts/surface_code_parent_memory/h5_end_to_end_baseline/process_tree_samples.jsonl` sibling `summary.json`
- Process tree samples: `/home/abe/Project/Evaluation_grouped_surface_code/artifacts/surface_code_parent_memory/h5_end_to_end_baseline/process_tree_samples.jsonl`
- Parent markers: `/home/abe/Project/Evaluation_grouped_surface_code/artifacts/surface_code_parent_memory/h5_end_to_end_baseline/parent_markers.jsonl`
- Stage metrics: `/home/abe/Project/Evaluation_grouped_surface_code/artifacts/surface_code_parent_memory/h5_end_to_end_baseline/stage_metrics.jsonl`
