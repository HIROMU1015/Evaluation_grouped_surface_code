# qret Optimization Integrity and Performance Summary

## 1. Scope

This report summarizes Evaluation/qret lightening through the Phase A instruction arena decision. Only H4 and H5 were executed in this pass; H6, H7, H8, and H9 were not executed.

## 2. Research Context

The benchmark covers the uncontrolled single-step grouped H-chain surface-code pipeline used by the existing Evaluation reports. It does not turn the workload into full QPE.

## 3. Baseline Selection

- earliest runnable baseline: `6011635af1db3b3c1c1fa38dbb6affcc9472ee7a`
- selected stable pre-optimization baseline: `5c52fc649d26c33f027d5ac65ef4f2f0701347d1`
- selected reason: build_qret.sh, qret vendoring, and profiling harness exist, but production qret memory optimizations had not started.

## 4. Final Production Configuration

- magic path storage: `interned`
- non-path operands: legacy containers
- compile-info output: `summary`
- summary TimeSeries: repository current production setting (`legacy_timeseries` in this benchmark env)
- DepGraph: `compact`
- inverse-map construction: eager default
- inverse-map release after routing: enabled
- pipeline-state output: skipped
- instruction allocation default: `legacy`

## 5. Optimization Inventory

| optimization | status | evaluation case | memory effect | elapsed effect | semantic validation | reason |
| ------------ | ------ | --------------- | ------------- | -------------- | ------------------- | ------ |
| streaming Python inliner | production adopted | H4/H5 pipeline tests and staged reports | reduced parent JSON/IR lifetime; report-level cumulative | preserved or improved by avoiding full merged IR materialization | normalized instruction stream and metrics | same inlining semantics with streaming emission |
| incremental JSON parsing | production adopted | H4 parent-RSS profile | reduced retained Python JSON load where used | small/acceptable | field extraction and normalized metrics | reads required fields without changing values |
| RZ helper independent/cache/batch/merge-less flow | production adopted | H4/H5 artifact generation | removes repeated full-IR helper materialization | warm/helper-cache improvement | helper output summaries and optimized IR stream hash | cache keys include input, qret hash, gridsynth identity, and version |
| integral cache | production adopted | surface-code reproducibility tests | avoids regeneration work on warm runs | warm prepare improvement | content/version keyed npz metadata | only exact cache-key hit is reused |
| prepared artifact cache / compile result cache | production adopted | architecture sweep cache-hit tests | warm run avoids prepared/compile intermediate regeneration | warm run improvement | artifact and compile cache hashes | cache payload includes qret/topology/config/input hashes |
| pipeline-state output skip | production adopted | H4/H5 qret direct benchmark | large qret peak reduction by avoiding BuildPipelineState | large compile elapsed reduction | compile-info metrics parity | compile-info is dumped directly; unused state output is not built |
| compile-info summary / summary aggregation / TimeSeries current default | production adopted | H4/H5/H6 summary reports, H6 predates current restriction | large compile-info JSON and summary accumulation reduction | improved or acceptable | raw and normalized metrics parity | keeps required aggregates without retaining full time-series payload |
| compact DepGraph | production adopted | H4/H5 compact graph profiles | reduced dependency graph storage | acceptable | node/edge counts and depth metrics parity | representation changes, graph semantics unchanged |
| inverse-map release after routing | production adopted | H5 routing lifetime profile | reduces allocator in-use bytes after routing | neutral | post-routing consumers do not require inverse maps | clears maps after the mutation phase |
| magic-path exact interning | production adopted | H5 `4th(new_2)` | 116.6 MB / 21.1% H5 qret peak reduction | improved | raw and normalized metrics parity | only identical path sequences share storage |
| non-path singleton operand compaction | evaluated and rejected | H5 `4th(new_2)` | 12.3 MB / 2.834% peak reduction | 9.092% regression | raw and normalized metrics parity | compatibility cache added object bytes and elapsed cost |
| lazy inverse-map construction | evaluated and rejected | H5 `4th(new_2)` | 48 KB / 0.011% peak reduction | 0.951% faster | raw and normalized metrics parity | removed live entries but did not move VMRSS high-water |
| instruction arena allocation | rejected | H4/H5 `4th(new_2)` | 10.8 MB / 2.487% H5 qret peak reduction | 2.314% faster in Phase A median | raw, normalized, and semantic projection parity | failed 30 MB or 7% H5 peak gate |

## 6. Semantic Preservation Arguments

The adopted changes alter storage, emission, caching, or aggregation paths, not the target circuit semantics. Cache reuse is guarded by content/config/version hashes. qret storage changes keep instruction ordering, pass order, topology options, and compile-info metric definitions stable. Arena mode was not adopted; it remains an explicit candidate with default legacy allocation.

## 7. Observational Equivalence

| case | raw metrics equal | normalized metrics equal | ignored normalized fields |
| ---- | ----------------- | ------------------------ | ------------------------- |
| `h4_2nd` | True | True | cache_key, compile_info_json, compiler_core_library_hash, compiler_core_library_path, compiler_executable_hash, compiler_executable_path, estimated_execution_time_sec, execution_time_sec |
| `h4_4th_new2` | True | True | cache_key, compile_info_json, compiler_core_library_hash, compiler_core_library_path, compiler_executable_hash, compiler_executable_path, estimated_execution_time_sec, execution_time_sec |
| `h5_4th_new2` | True | True | cache_key, compile_info_json, compiler_core_library_hash, compiler_core_library_path, compiler_executable_hash, compiler_executable_path, estimated_execution_time_sec, execution_time_sec |

The claim is limited to observational equivalence for the measured H4/H5 pipelines and the unit/integration tests. This is not a formal proof for every possible quration input.

## 8. Test Coverage

Coverage includes focused Python report tests, Phase A arena tests, qret C++ target tests, and the final full pytest/CTest verification listed in the task log.

## 9. Individual Optimization Results

The cumulative result must be read baseline-vs-final; individual percentage reductions are not additive. Rejected candidates remain listed above.

## 10. Baseline Vs Final Benchmark Method

- baseline qret: selected worktree at `5c52fc6`
- final qret: current Evaluation worktree build
- common input: final prepared optimized IR for each case
- common external metrics: `/usr/bin/time -v`, process-tree sampler, elapsed wall clock, compile-info size, intermediate file sizes
- cold/warm definition: qret direct compile has no application-level compile-result cache in this harness; warm is the immediate second direct compile on the same input and output shape. OS page cache was not dropped.
- baseline qret executable hash: `3ccf60ae369ea27317e9b532eae2fa3951e17043071a0b1eea4cfbc7ca1435a3`
- final qret executable hash: `d519cdb25446cf243053e84ffa559b7e6bd7dbd66365e1488d632208616dbbf5`
- topology hash: `b7a81d54181fdc7985f026501290417a9bf8356773b7113466245d452b253b89`
- Python: `3.11.1 (main, Nov 18 2024, 15:05:59) [GCC 11.4.0]`
- compiler: `c++ (Ubuntu 11.4.0-1ubuntu1~22.04) 11.4.0`
- MemTotal KB: `65522476`

## 11. H4 Results

### H4 Cold

| metric | baseline | final | absolute difference | percentage |
| ------ | -------: | ----: | ------------------: | ---------: |
| `elapsed_seconds` | 7.130 | 4.921 | 2.209 | 30.982% |
| `qret_peak_rss_kb` | 2,089,188 | 171,440 | 1,917,748 | 91.794% |
| `tree_peak_rss_kb` | 2,081,748 | 172,464 | 1,909,284 | 91.715% |
| `compile_info_size_bytes` | 18.09 | <0.01 | 18.09 | 99.989% |
| `largest_intermediate_file_bytes` | 18.09 | 8.31 | 9.78 | 54.044% |
| `total_intermediate_file_bytes` | 34.66 | 16.58 | 18.09 | 52.184% |

### H4 Warm

| metric | baseline | final | absolute difference | percentage |
| ------ | -------: | ----: | ------------------: | ---------: |
| `elapsed_seconds` | 7.159 | 4.914 | 2.245 | 31.358% |
| `qret_peak_rss_kb` | 2,089,232 | 171,376 | 1,917,856 | 91.797% |
| `tree_peak_rss_kb` | 2,081,644 | 172,400 | 1,909,244 | 91.718% |
| `compile_info_size_bytes` | 18.09 | <0.01 | 18.09 | 99.989% |
| `largest_intermediate_file_bytes` | 18.09 | 8.31 | 9.78 | 54.044% |
| `total_intermediate_file_bytes` | 34.66 | 16.58 | 18.09 | 52.184% |

## 12. H5 Results

### H5 Cold

| metric | baseline | final | absolute difference | percentage |
| ------ | -------: | ----: | ------------------: | ---------: |
| `elapsed_seconds` | 20.893 | 19.169 | 1.724 | 8.251% |
| `qret_peak_rss_kb` | 5,484,042 | 435,258 | 5,048,784 | 92.063% |
| `tree_peak_rss_kb` | 5,473,618 | 436,410 | 5,037,208 | 92.027% |
| `compile_info_size_bytes` | 57.91 | <0.01 | 57.91 | 99.996% |
| `largest_intermediate_file_bytes` | 57.91 | 22.05 | 35.86 | 61.926% |
| `total_intermediate_file_bytes` | 102.45 | 44.54 | 57.91 | 56.525% |

### H5 Warm

| metric | baseline | final | absolute difference | percentage |
| ------ | -------: | ----: | ------------------: | ---------: |
| `elapsed_seconds` | 20.889 | 18.979 | 1.910 | 9.145% |
| `qret_peak_rss_kb` | 5,483,526 | 435,282 | 5,048,244 | 92.062% |
| `tree_peak_rss_kb` | 5,473,156 | 436,562 | 5,036,594 | 92.024% |
| `compile_info_size_bytes` | 57.91 | <0.01 | 57.91 | 99.996% |
| `largest_intermediate_file_bytes` | 57.91 | 22.05 | 35.86 | 61.926% |
| `total_intermediate_file_bytes` | 102.45 | 44.54 | 57.91 | 56.525% |

## 13. Cold Vs Warm Results

| aggregate | runs | median elapsed s | median qret peak KB | median tree peak KB |
| --------- | ---: | ---------------: | ------------------: | ------------------: |
| `h4_2nd:baseline:cold` | 1 | 1.344 | 450,844 | 452,124 |
| `h4_2nd:baseline:warm` | 1 | 1.307 | 450,800 | 452,080 |
| `h4_2nd:final:cold` | 1 | 0.768 | 42,600 | 43,880 |
| `h4_2nd:final:warm` | 1 | 0.765 | 42,584 | 43,864 |
| `h4_4th_new2:baseline:cold` | 3 | 7.130 | 2,089,188 | 2,081,748 |
| `h4_4th_new2:baseline:warm` | 3 | 7.159 | 2,089,232 | 2,081,644 |
| `h4_4th_new2:final:cold` | 3 | 4.921 | 171,440 | 172,464 |
| `h4_4th_new2:final:warm` | 3 | 4.914 | 171,376 | 172,400 |
| `h5_4th_new2:baseline:cold` | 2 | 20.893 | 5,484,042 | 5,473,618 |
| `h5_4th_new2:baseline:warm` | 2 | 20.889 | 5,483,526 | 5,473,156 |
| `h5_4th_new2:final:cold` | 2 | 19.169 | 435,258 | 436,410 |
| `h5_4th_new2:final:warm` | 2 | 18.979 | 435,282 | 436,562 |

## 14. Memory Reduction

The direct observed memory reduction is reported in the H4/H5 tables above. The largest qret-side reductions came from skipping unused pipeline-state construction/output, compile-info summary aggregation, compact DepGraph, inverse-map release for allocator in-use bytes, and exact magic-path interning.

## 15. Elapsed-Time Reduction

Elapsed reductions are reported as direct baseline-vs-final medians in the H4/H5 tables. Warm Python cache wins are summarized qualitatively from the adopted cache mechanisms because this direct qret harness intentionally bypasses Evaluation compile-result cache.

## 16. Intermediate-File Reduction

The direct file-size reductions are dominated by full baseline compile-info JSON versus final summary compile-info JSON. Missing pipeline-state output is reported as not generated, not as zero semantic output.

## 17. Rejected Candidates

- non-path singleton operand compaction: rejected for small peak saving and elapsed regression.
- lazy inverse-map construction: rejected for negligible VMRSS peak movement.
- instruction arena allocation: rejected for failing the H5 30 MB / 7% peak gate.

## 18. Remaining Bottlenecks

H5 high-water is now dominated by MachineFunction construction and retained instruction/operand/list-node layout. Arena allocation alone did not remove enough resident memory; larger representation or ownership changes remain higher risk follow-up work.

## 19. Remaining Research Approximations

- uncontrolled 1 Trotter step is the central measured workload
- full QPE circuit was not compiled
- controlled-U, QPE ancillae, inverse QFT, and measurement feed-forward are not included
- multiple-step non-additive effects and factory stock state across steps remain unevaluated
- H6-H9 were not executed; H9 must remain estimated/theoretical only

## 20. Limitations

The direct benchmark compares qret compile stages on shared final optimized IR. It does not re-run the full cold Python artifact-generation pipeline for baseline because that would mix older instrumentation and cache semantics with the qret-side comparison.

## 21. Conclusion

Lightening preserves the target observables in the measured H4/H5 pipeline, but the original resource-estimation model approximations remain. Phase A ended with arena rejected and production default unchanged.
