# Surface-Code RSS Memory Profile

## Purpose

This profile separates Python parent current RSS, Python parent lifetime
`ru_maxrss`, qret subprocess max RSS, and stage-local RSS deltas before choosing
the next RSS reduction target.

## Commit And Environment

- Base commit at measurement start: `b9a4b55 Add surface-code stage profiling`
- Repository: `HIROMU1015/Evaluation_grouped_surface_code`
- qret: `build/quration/qret`
- Topology: `third_party/quration/quration-core/examples/data/topology/tutorial.yaml`
- RSS sampling: enabled through `SURFACE_CODE_PROFILE_RSS_SAMPLING=1`
- Sampling interval: 20 ms
- Unit: KB unless otherwise stated

The raw benchmark JSON/CSV files were written under `benchmark_results/`, which
is ignored by Git. Only this summarized report is tracked.

## Measurement Method

- Parent current RSS is read from `/proc/self/status` `VmRSS`.
- Parent lifetime high-water RSS uses `resource.getrusage(...).ru_maxrss`.
- Parent sampled peak RSS is a low-frequency per-stage current RSS sample.
- qret subprocess max RSS is read through `/usr/bin/time -v` when qret is run.
- qret internal mapping/routing/QEC pass RSS is not exposed; it is measured only
  as part of the outer `qret_compile` subprocess.

## H4 Stage Results

| case | prepare elapsed | compile elapsed | compile cache hit | slowest stage | sampled parent RSS peak | largest current RSS delta | qret subprocess RSS peak |
| --- | ---: | ---: | --- | --- | --- | --- | --- |
| H4 2nd, batch1, cold, topology | 8.014s | 1.382s | false | `compile:qret_compile` 1.339s | `compile:read_compile_info_json` 289280 | `prepare:build_step_circuit` +40192 | `compile:qret_compile` 450852 |
| H4 2nd, batch2, cold, topology | 7.807s | 1.411s | false | `compile:qret_compile` 1.366s | `compile:read_compile_info_json` 286160 | `prepare:build_step_circuit` +40448 | `compile:qret_compile` 451364 |
| H4 4th(new_2), batch2, cold, topology | 24.489s | 6.949s | false | `compile:qret_compile` 6.764s | `compile:read_compile_info_json` 343828 | `prepare:basis_circuit` +46836 | `compile:qret_compile` 2089792 |
| H4 4th(new_2), batch4, cold, topology | 24.369s | 6.993s | false | `compile:qret_compile` 6.811s | `compile:read_compile_info_json` 339964 | `prepare:basis_circuit` +46620 | `compile:qret_compile` 2089920 |
| H4 4th(new_2), batch2, hot, topology | 0.693s | 0.184s | true | `compile:read_compile_info_json` 0.174s | `compile:read_compile_info_json` 289548 | `compile:read_compile_info_json` +51812 | N/A |
| H4 4th(new_2), batch2, hot prepare + QEC compile | 0.690s | 6.766s | false | `compile:qret_compile` 6.579s | `compile:read_compile_info_json` 271712 | `compile:read_compile_info_json` +52016 | `compile:qret_compile` 2090516 |

## H4 4th(new_2) Cold Stage Detail

For the H4 4th batch2 cold topology run:

| stage | elapsed | current RSS before | current RSS after | current delta | sampled peak | subprocess max RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `prepare:build_step_circuit` | 0.602s | 222560 | 262752 | +40192 | 262752 | N/A |
| `prepare:basis_circuit` | 2.343s | 262752 | 309588 | +46836 | 309632 | N/A |
| `prepare:qret_parse` | 0.444s | 309588 | 309588 | 0 | 309588 | 203100 |
| `prepare:load_rz_helper_full_ir` | 0.134s | 313156 | 324544 | +11388 | 324544 | N/A |
| `prepare:qret_opt_rz_helper_batch_*` | about 0.07-0.15s each | about 325000-329000 | no stage-local jump | 0 | about 325000-329000 | about 10752-13056 |
| `prepare:qret_opt_main_cleanup` | 0.374s | 313400 | 313400 | 0 | 313400 | 158572 |
| `prepare:python_streaming_inline` | 3.975s | 313400 | 315960 | +2560 | 315960 | N/A |
| `compile:qret_compile` | 6.764s | 315960 | 315960 | 0 | 315960 | 2089792 |
| `compile:read_compile_info_json` | 0.173s | 315960 | 343828 | +27868 | 343828 | N/A |

## File Sizes And Circuit Size

For H4 4th(new_2), batch2 cold topology:

| item | value |
| --- | ---: |
| `step.qasm` | 1137885 bytes |
| `step_ir.json` | 7520490 bytes |
| `step_opt.json` | 8717975 bytes |
| `compile_info.json` | 18970408 bytes |
| `step_artifact.json` | 480043 bytes |
| flat instruction count | 401906 |
| gate depth | 236096 |
| magic-state count | 91300 |
| magic-state depth | 87032 |
| peak magic layer | 8 |
| normalized stream hash | `0bbe2b55ad5334a8bb06df5b500a6c05905767237e1fd21766a9fab0ec63e320` |

## `step_ir.json` Load Isolation

Input: H4 4th(new_2) `step_ir.json`, 7520490 bytes.

| mode | elapsed | current RSS delta | current RSS delta after GC | `ru_maxrss` delta | circuits | helpers | extracted instructions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| full `json.load()` | 0.119s | +3412 | +3412 | +12216 | 190 | 189 | 82473 |
| circuit scan only | 0.078s | +112 | -280 | +6288 | 190 | 189 | 82473 |
| helpers only | 0.080s | +512 | 0 | 0 | 190 | 189 | 380 |
| main metadata only | 0.081s | +1092 | +1092 | +7400 | 190 | 189 | 82093 |

Observation: incremental circuit scanning reduces retained current RSS compared
with full `json.load()`, but the measured H4 whole-pipeline peak is dominated by
qret compile subprocess RSS and by Qiskit circuit/basis construction in the
Python parent. Therefore this does not yet justify a large IR representation
change; a small incremental helper extraction remains plausible.

## Answers To Key Questions

1. **First H4 prepare stage that raises RSS high-water**: `build_step_circuit`
   raises current RSS by about 40 MB, then `basis_circuit` raises it by another
   about 47 MB. These are the first large Python-parent retained increases.
2. **Stages that leave RSS retained after completion**: `build_step_circuit`,
   `basis_circuit`, `load_rz_helper_full_ir`, and `read_compile_info_json` show
   positive current RSS deltas. The qret subprocess stages do not raise parent
   current RSS materially.
3. **Is full `step_ir.json` load the main peak cause?** Not for the measured H4
   runs. It contributes about +11 MB in `load_rz_helper_full_ir`, while qret
   compile subprocess reaches about 2.09 GB and circuit/basis construction
   retains about 87 MB combined.
4. **Does RZ helper batch size affect RSS?** H4 2nd batch1 vs batch2 are almost
   identical in RSS. H4 4th batch2 vs batch4 are also almost identical in RSS.
   Batch size mainly affects qret launch count/time, not the observed peak RSS.
5. **Why are cold and hot RSS close?** Hot runs skip circuit/helper generation
   but still load existing artifacts and parse the large `compile_info.json`.
   Python allocator high-water behavior also means `ru_maxrss` remains less
   informative than current RSS deltas.
6. **Prepare or compile creates the overall peak?** For H4 4th, qret compile
   subprocess creates the largest overall RSS value, about 2.09 GB. For the
   Python parent only, `read_compile_info_json` and earlier circuit/basis stages
   determine the high current RSS.
7. **Python parent or qret subprocess is dominant?** Overall RSS is dominated by
   qret subprocess during compile. Parent Python retained RSS is still relevant
   but smaller, around 340 MB sampled peak in this H4 run.
8. **Does the dominant stage change from H2 to H4?** Yes. H2 was too small to
   identify H4 behavior. H4 compile shows qret subprocess RSS dominance.
9. **Evaluation-side reducible RSS**: circuit/basis object lifetime,
   `load_rz_helper_full_ir`, and `compile_info.json` loading are Evaluation-side
   candidates. The 2 GB qret compile subprocess peak is outside the Python
   wrapper.
10. **Boundary requiring qret internal changes**: mapping/routing/QEC pass RSS
    inside `qret_compile` cannot be split further from Evaluation. Reducing that
    peak requires qret-side instrumentation or implementation changes.

## Optimization Ranking

| candidate | target | evidence | implementation size | semantic risk | recommendation |
| --- | --- | --- | --- | --- | --- |
| circuit/basis object early release | Python parent RSS | `build_step_circuit` +40 MB and `basis_circuit` +47 MB retained | small | low | recommended first for Python RSS |
| incremental helper extraction | Python parent RSS | `load_rz_helper_full_ir` +11 MB; isolated scan retains less RSS than full load | small-medium | low | useful but not first |
| compile_info streaming/minimal parse | Python parent RSS | `read_compile_info_json` +28-52 MB and 19 MB file | small-medium | low | recommended for hot/compile-only RSS |
| prepare/compile separate process | parent high-water isolation | parent RSS carries from prepare into compile in same process | medium | low-medium | useful for measurement or production isolation, not semantic optimization |
| flat IR representation change | Python/qret RSS | current file load is not dominant versus qret compile | large | medium-high | not recommended yet |
| qret internal mapping/routing/QEC changes | subprocess RSS | `qret_compile` reaches about 2.09 GB | large | high | needs qret-side profiling first |

## Unconfirmed

- H5/H6 behavior was not measured in this pass.
- H4 4th batch1 cold was not run because it would require many qret helper
  invocations; H4 2nd batch1 and H4 4th batch2/batch4 were used as representative
  points.
- qret internal pass-by-pass RSS remains unavailable from Evaluation-side
  instrumentation.
