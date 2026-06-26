# Surface-Code Stage Profiling Report

## Purpose

Identify which prepare and compile stages dominate wall time and peak RSS without adding a new optimization based on guesswork.

## Target Commit

- Commit: `6011635af1db3b3c1c1fa38dbb6affcc9472ee7a`
- Dirty status: `M .gitignore
 M README.md
 M configs/surface_code_architecture_sweep.yaml
 M src/trotterlib/architecture_sweep.py
 M src/trotterlib/surface_code.py
 M tests/test_surface_code_streaming_inliner.py
?? docs/
?? scripts/profile_surface_code_stages.py
?? src/trotterlib/profiling.py`

## Environment

- Python: `3.11.1 (main, Nov 18 2024, 15:05:59) [GCC 11.4.0]`
- Platform: `Linux-6.8.0-47-generic-x86_64-with-glibc2.35`
- qret: `/home/abe/Project/Evaluation_grouped_surface_code/build/quration/qret`
- qret hash: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- Topology: `/home/abe/Project/Evaluation_grouped_surface_code/third_party/quration/quration-core/examples/data/topology/tutorial.yaml`
- RZ helper batch size: `2`

## Method

- Prepare metrics are read from `prepare_stage_metrics.json` or `prepare_stage_cache_hit_metrics.json`.
- Compile metrics are read from `compile_stage_metrics.json` or `compile_stage_cache_hit_metrics.json`.
- Python RSS uses `resource.getrusage(...).ru_maxrss` and is stored in KB.
- qret subprocess RSS uses `/usr/bin/time -v` when available and is stored in KB.
- Mapping, routing, and QEC elapsed are not split unless qret exposes them; otherwise they are included in `qret_compile`.

## Result Summary

| case | cache | compile mode | prepare elapsed | compile elapsed | stream hash |
| --- | --- | --- | --- | --- | --- |
| H2_2nd_ftqc_compile_topology_current-cache-state | current-cache-state | ftqc_compile_topology | 0.680s | 0.003s | `1878871c2a08e5c1cd82e774851c50e5910fe54279de826ee4df4fb79fd066e6` |
| H2_2nd_ftqc_compile_topology_qec_current-cache-state | current-cache-state | ftqc_compile_topology_qec | 0.004s | 0.065s | `1878871c2a08e5c1cd82e774851c50e5910fe54279de826ee4df4fb79fd066e6` |
| H2_4th(new_2)_ftqc_compile_topology_current-cache-state | current-cache-state | ftqc_compile_topology | 0.004s | 0.009s | `4c1a74f59ff19aaae9e3d7efd7bd1905bd87793fd19774c97d318480d79f457f` |
| H2_4th(new_2)_ftqc_compile_topology_qec_current-cache-state | current-cache-state | ftqc_compile_topology_qec | 0.004s | 0.218s | `4c1a74f59ff19aaae9e3d7efd7bd1905bd87793fd19774c97d318480d79f457f` |

## Baseline Reference

These values are prior H4 observations and are not directly comparable to the measurements above unless rerun under the same commit, cache state, and environment.

| item | value |
| --- | --- |
| legacy RZ helper full-IR prepare | H4 about 98.4s |
| current cold prepare | H4 about 24.9s |
| current hot prepare | H4 about 12.2s |
| legacy RZ helper opt | about 88.8s, 186 qret launches |
| batched RZ helper opt | about 12.7s, 6 qret launches |
| legacy full-IR peak RSS | about 335 MiB |
| current cold peak RSS | about 333 MiB |
| current hot peak RSS | about 327 MiB |

## Observed Facts

- Slowest recorded stage: qret_compile, elapsed=0.210s, python_rss=218988KB, subprocess_rss=86008KB.
- Highest Python parent RSS stage: read_compile_info_json, elapsed=0.007s, python_rss=218988KB.
- Highest qret subprocess RSS stage: qret_compile, elapsed=0.210s, python_rss=218988KB, subprocess_rss=86008KB.

## Interpretation

- Treat the rows above as observations for the listed commit and cache state only.
- If `subprocess_maxrss_kb` is missing, `/usr/bin/time -v` was unavailable or the stage did not launch qret.
- If `qret_compile` dominates elapsed or subprocess RSS, the next boundary is inside qret rather than the Evaluation Python wrapper.
- For small H2 profiles, do not extrapolate RSS or routing behavior to H4 without rerunning H4 under the same conditions.
- A flat Python parent high-water mark does not by itself prove that `step_ir.json` full-load is or is not the dominant H4 RSS source.

## Judgment Items

| question | current answer |
| --- | --- |
| prepare stage creating peak RSS | Unconfirmed for H4 unless an H4 run is present in this report. |
| qret subprocess vs Python parent | Compare `Highest Python parent RSS stage` and `Highest qret subprocess RSS stage`; note that they use separate semantics. |
| value of optimizing `step_ir.json` full-load | Only justified if Python parent RSS rises in IR load/inline stages for H4. |
| main cleanup or qret parse dominance | Use the stage rows; do not infer dominance when elapsed is unavailable. |
| streaming inliner impact | Requires comparison against legacy inliner metrics; semantic hashes here only verify stability. |
| mapping/routing major constraint size | Unconfirmed unless qret exposes finer elapsed or larger cases are run. |
| Evaluation vs Quration boundary | Evaluation records wrapper stages; finer mapping/routing/QEC attribution requires qret-side instrumentation. |

## Open Items

- Full H4/H5/H6 cold and hot matrices should be run only when runtime budget allows.
- qret does not currently expose mapping/routing/QEC elapsed at separate stage granularity.

## Next Optimization Candidates

- Optimize the stage that dominates in this report, after confirming it also dominates H4.
- Consider `step_ir.json` input-side parsing only if Python parent RSS rises during IR load/inline stages rather than qret subprocess stages.

## Optimizations Not Yet Justified

- Do not rewrite routing or qret internals based only on Python-side RSS.
- Do not add compact binary IR until JSON file size or parse RSS is confirmed dominant.
