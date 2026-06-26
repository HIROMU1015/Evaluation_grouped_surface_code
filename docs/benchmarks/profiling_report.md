# Surface-Code RSS Profiling Report

## Purpose

Identify the stages and processes that create peak RSS before choosing the next RSS-reduction implementation. This report separates parent Python current RSS, parent Python lifetime high-water RSS, sampled parent RSS peaks, and qret subprocess max RSS.

## Target

- Repository: `HIROMU1015/Evaluation_grouped_surface_code`
- Measurement base: `b9a4b555e379ae783156a0f27838b1ba0fe8345d` plus the profiling instrumentation in this change
- qret: `build/quration/qret`
- qret hash: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- Topology: `third_party/quration/quration-core/examples/data/topology/tutorial.yaml`
- RSS sampling: enabled in `scripts/profile_surface_code_stages.py`, 20 ms interval

## Method

- Parent current RSS is read from `/proc/self/status` `VmRSS`.
- Parent high-water RSS is `resource.getrusage(...).ru_maxrss`.
- qret subprocess RSS is parsed from `/usr/bin/time -v` when available.
- Stage-level sampled peak RSS is collected only when `SURFACE_CODE_PROFILE_RSS_SAMPLING=1`.
- Cold runs used isolated cache roots under `benchmark_results/profiling_caches/`; existing project caches were not deleted.
- Raw benchmark files remain under ignored `benchmark_results/`; only this report is committed.

## Cases

| case | cache/batch | compile mode | prepare s | compile s | instructions | magic | slowest stage | sampled parent peak KB | largest current RSS delta KB | qret max RSS KB |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| H2 2nd | cold, batch2 | `ftqc_compile_topology` | 1.856 | 0.064 | 3,648 | 1,208 | `qret_opt_rz_helper_batch_0000` | 267,212 | 39,680 (`build_step_circuit`) | 31,272 |
| H2 4th(new_2) | cold, batch2 | `ftqc_compile_topology` | 2.474 | 0.207 | 12,750 | 3,968 | `qret_compile` | 269,004 | 512 (`ir_rotation_precision_rewrite`) | 85,620 |
| H4 2nd | cold, batch1 | `ftqc_compile_topology` | 8.014 | 1.382 | 84,148 | 19,848 | `qret_compile` | 289,280 | 40,192 (`build_step_circuit`) | 450,852 |
| H4 2nd | cold, batch2 | `ftqc_compile_topology` | 7.807 | 1.411 | 84,148 | 19,848 | `qret_compile` | 286,160 | 40,448 (`build_step_circuit`) | 451,364 |
| H4 4th(new_2) | cold, batch2 | `ftqc_compile_topology` | 24.489 | 6.949 | 401,906 | 91,300 | `qret_compile` | 343,828 | 46,836 (`basis_circuit`) | 2,089,792 |
| H4 4th(new_2) | cold, batch4 | `ftqc_compile_topology` | 24.369 | 6.993 | 401,906 | 91,300 | `qret_compile` | 339,964 | 46,620 (`basis_circuit`) | 2,089,920 |
| H4 4th(new_2) | hot, batch2 | `ftqc_compile_topology` | 0.693 | 0.184 | 401,906 | 91,300 | `read_compile_info_json` | 289,548 | 51,812 (`read_compile_info_json`) | N/A |
| H4 4th(new_2) | hot prepare, batch2 | `ftqc_compile_topology_qec` | 0.690 | 6.766 | 401,906 | 91,300 | `qret_compile` | 271,712 | 52,016 (`read_compile_info_json`) | 2,090,516 |

## File Sizes

| case | `step.qasm` | `step_ir.json` | `step_opt.json` | `compile_info.json` |
| --- | ---: | ---: | ---: | ---: |
| H4 2nd batch2 | 230,058 B | 1,518,051 B | 1,823,393 B | 4,063,162 B |
| H4 4th(new_2) batch2 | 1,137,885 B | 7,520,490 B | 8,717,975 B | 18,970,408 B |

## Key H4 Stage Details

For H4 4th(new_2), cold batch2:

| stage | elapsed s | current before KB | current after KB | current delta KB | sampled peak KB | subprocess max RSS KB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `build_step_circuit` | 0.602 | 222,560 | 262,752 | 40,192 | 262,752 | N/A |
| `basis_circuit` | 2.343 | 262,752 | 309,588 | 46,836 | 309,632 | N/A |
| `qret_parse` | 0.444 | 309,588 | 309,588 | 0 | 309,588 | 203,100 |
| `load_rz_helper_full_ir` | 0.134 | 313,156 | 324,544 | 11,388 | 324,544 | N/A |
| RZ helper batch opt stages | about 0.07-0.15 each | about 325,056-329,664 | same | mostly 0 | about 325,056-329,664 | about 10,752-13,056 |
| `qret_opt_main_cleanup` | 0.374 | 313,400 | 313,400 | 0 | 313,400 | 158,572 |
| `python_streaming_inline` | 3.975 | 313,400 | 315,960 | 2,560 | 315,960 | N/A |
| `qret_compile` | 6.764 | 315,960 | 315,960 | 0 | 315,960 | 2,089,792 |
| `read_compile_info_json` | 0.173 | 315,960 | 343,828 | 27,868 | 343,828 | N/A |

## `step_ir.json` Read Isolation

Input: H4 4th(new_2) `step_ir.json`, 7,520,490 B, 190 circuits, 189 helper circuits.

| method | elapsed s | current RSS delta KB | delta after `gc.collect()` KB | `ru_maxrss` delta KB | extracted instructions |
| --- | ---: | ---: | ---: | ---: | ---: |
| full `json.load()` | 0.119 | 3,412 | 3,412 | 12,216 | 82,473 |
| circuit scan only | 0.078 | 112 | -280 | 6,288 | 82,473 |
| helpers only | 0.080 | 512 | 0 | 0 | 380 |
| main metadata only | 0.081 | 1,092 | 1,092 | 7,400 | 82,093 |

Observation: incremental scanning is lighter than full `json.load()`, but for H4 4th(new_2) the isolated `step_ir.json` full load is not the dominant RSS source. The qret compile subprocess peak is about 2.09 GB, while the parent Python sampled peak is about 344 MB.

## Answers

| question | answer |
| --- | --- |
| H4 prepare stage that first raises RSS high-water | `build_step_circuit` raises current RSS by about 40 MB, then `basis_circuit` raises it by about 47 MB. |
| Stage retaining RSS after completion | Parent current RSS remains elevated after circuit construction and after `read_compile_info_json`; `load_rz_helper_full_ir` adds about 11 MB in the cold H4 4th run. |
| Is full `step_ir.json` load the main peak source? | No for measured H4. It is measurable but much smaller than qret compile subprocess RSS and circuit construction retained RSS. |
| Does RZ helper batch size affect RSS? | Not materially in measured cases. H4 2nd batch1 vs batch2 and H4 4th batch2 vs batch4 have nearly identical parent RSS and qret compile RSS. |
| Why cold/hot RSS difference is small | Hot prepare skips heavy generation, but the Python process still imports the same libraries and compile cache hit still reads large `compile_info.json`; `ru_maxrss` is also a process lifetime high-water mark. |
| Prepare or compile creates overall peak? | For H4 4th, qret compile subprocess creates the overall RSS peak. Parent Python peak is later observed around `read_compile_info_json`. |
| Python parent or qret subprocess dominates? | qret subprocess dominates for H4 topology/QEC compile: about 2.09 GB vs parent Python about 0.34 GB. |
| Does dominance change from H2 to H4? | Yes. H2 peaks are modest; H4 4th qret compile subprocess RSS dominates strongly. |
| Evaluation-side reducible RSS | Circuit object lifetime, basis circuit/transpiled circuit retention, `compile_info.json` load, and small IR load improvements. |
| Boundary requiring qret changes | mapping/routing/QEC compile memory inside `qret_compile`; Evaluation can measure it but cannot split or reduce it without qret-side instrumentation or implementation changes. |

## Optimization Ranking

| candidate | estimated target | evidence | implementation size | semantic risk | recommendation |
| --- | --- | --- | --- | --- | --- |
| circuit object early release | Python parent RSS | `build_step_circuit` and `basis_circuit` add about 40-47 MB current RSS each in H4 4th. | small | low | recommended next Evaluation-side cleanup |
| compile_info streaming/summary extraction | Python parent RSS | `read_compile_info_json` adds about 28-52 MB current RSS and `compile_info.json` is 18.97 MB for H4 4th. | small-medium | low | recommended after circuit release |
| incremental helper extraction | Python parent RSS | Isolated full `step_ir.json` load adds about 3.4 MB current RSS and 12.2 MB `ru_maxrss`; scan-only is lighter. | small-medium | low | not first priority |
| prepare/compile separate processes | parent high-water isolation | Separates parent high-water marks, but qret subprocess still dominates H4 compile RSS. | medium | low-medium | useful for measurement isolation, not primary RSS reduction |
| flat IR representation change | Python/qret RSS | Current evidence does not show flat IR JSON as the dominant H4 peak source. | large | medium-high | not recommended now |
| qret internal instrumentation/change | subprocess RSS | qret compile subprocess reaches about 2.09 GB in H4 4th topology/QEC compile. | large | high | needed only after deciding to attack compile-side memory |

## Unconfirmed

- H5/H6 were not run in this pass.
- qret internal mapping/routing/QEC pass-by-pass RSS remains unavailable from Evaluation.
- `gc.collect()` experiments were limited to isolated JSON loading; production code was not changed to call GC.
